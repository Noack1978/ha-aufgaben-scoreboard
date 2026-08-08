"""
Zentrale Datenverwaltung der Integration "Aufgaben-Punktesystem".

Diese Klasse (AufgabenScoreboardManager) ist das Herzstück der
Integration. Sie hält alle Aufgaben, Zuweisungen, Erledigungen und
Punktestände im Arbeitsspeicher, kümmert sich um das dauerhafte
Speichern (über den Home-Assistant "Store"-Helper als JSON-Datei in
.storage/) und benachrichtigt bei Änderungen alle abhängigen
Entitäten (Sensoren) sowie das Frontend über den Dispatcher.

Der Manager kennt KEINE Home-Assistant-Plattformen (Sensor o. Ä.)
direkt - er stellt nur Daten und Methoden bereit. Das hält die Logik
sauber testbar und getrennt von der eigentlichen Entity-Darstellung.
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.helpers.storage import Store

from .const import (
    EVENT_COMPLETION_UNDONE,
    EVENT_TASK_ADDED,
    EVENT_TASK_APPROVED,
    EVENT_TASK_ASSIGNED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_COMPLETION_REQUESTED,
    EVENT_TASK_REJECTED,
    EVENT_TASK_REMOVED,
    EVENT_TASK_UPDATED,
    EVENT_TEMPLATE_ADDED,
    EVENT_TEMPLATE_REMOVED,
    EVENT_TEMPLATE_UPDATED,
    SCHEDULE_TYPE_DAYS,
    SCHEDULE_TYPE_WEEKLY,
    SIGNAL_UPDATE,
    STORAGE_KEY,
    STORAGE_VERSION,
    TASK_STATUS_DONE,
    TASK_STATUS_OPEN,
    TASK_STATUS_PENDING_APPROVAL,
    UNDO_ANZAHL_LIMIT,
    UNDO_ZEITLIMIT_TAGE,
)

_LOGGER = logging.getLogger(__name__)


def _jetzt_iso() -> str:
    """Gibt den aktuellen Zeitpunkt als ISO-8601-String (UTC) zurück."""
    return datetime.now(timezone.utc).isoformat()


def _heute_iso() -> str:
    """Gibt das aktuelle Datum (in der HA-konfigurierten Zeitzone) als ISO-8601-Datum zurück."""
    return dt_util.now().date().isoformat()


class AufgabenScoreboardManager:
    """
    Verwaltet Aufgaben, Zuweisungen und Punktestände der Integration.

    Datenstruktur (self._data), die 1:1 in der Storage-Datei landet:

    {
        "tasks": {
            "<task_id>": {
                "id": "<task_id>",
                "name": "Küche aufräumen",
                "description": "Geschirrspüler ein-/ausräumen",
                "score": 10,
                "assigned_to": ["<user_id_1>", "<user_id_2>"],
                "created_at": "2026-01-01T10:00:00+00:00",
                "status": "open",  # oder "done"
                "template_id": "<template_id>" oder None,  # Ursprung, falls
                    # aus einer Standardaufgabe erzeugt (manuell per Button
                    # oder automatisch per Entitäts-Trigger) - wird u. a.
                    # für den Duplikat-Schutz beim Trigger benötigt.
            },
            ...
        },
        "completions": [
            {
                "task_id": "...",
                "task_name": "...",
                "user_id": "...",
                "score": 10,
                "completed_at": "...",
            },
            ...
        ],
        "scores": {
            "<user_id>": 42,
            ...
        },
        "templates": {
            "<template_id>": {
                "id": "<template_id>",
                "name": "Rasen mähen",
                "description": "...",
                "score": 10,
                "assigned_to": ["<user_id_1>", "<user_id_2>"],
                "multiscoring": False,  # True = beim Anlegen entsteht PRO
                    # zugewiesenem Benutzer eine eigene, unabhängig
                    # erledigbare Aufgabe (statt einer gemeinsamen)
                "trigger_entity_id": "<entity_id>" oder None,  # optional:
                    # automatische Anlage, sobald diese Entität den unten
                    # angegebenen Zustand erreicht
                "trigger_state": "<zielzustand>" oder None,
                "schedule_type": "days" | "weekly" | None,  # optional:
                    # automatische Anlage nach Zeitplan (zusätzlich und
                    # unabhängig vom Entitäts-Trigger nutzbar)
                "schedule_interval": 1,  # bei "days": alle X Tage;
                    # bei "weekly": alle X Wochen (1 = jede Woche)
                "schedule_weekday": 0,  # nur bei "weekly": Wochentag
                    # (0=Montag ... 6=Sonntag)
                "schedule_anchor": "2026-01-01",  # Referenzdatum, ab dem
                    # das Tage-/Wochen-Intervall gezählt wird - wird beim
                    # Anlegen bzw. bei jeder Änderung der Zeitplan-Konfiguration
                    # auf "heute" gesetzt
                "schedule_last_triggered": "2026-01-01" oder None,  # Datum
                    # der letzten Zeitplan-Anlage - verhindert eine zweite
                    # Anlage am selben Tag, selbst wenn die zuvor erzeugte
                    # Aufgabe zwischenzeitlich bereits erledigt wurde
                "created_at": "...",
            },
            ...
        },
    }
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = {
            "tasks": {},
            "completions": [],
            "scores": {},
            "templates": {},
        }
        # Abmelde-Funktionen der aktuell abonnierten Entitäts-Trigger,
        # nach template_id - siehe sync_trigger_listeners().
        self._trigger_unsub: dict[str, Any] = {}
        # Abmelde-Funktion des täglichen Zeitplan-Listeners - siehe
        # async_setup_schedule().
        self._schedule_unsub: Any = None

    # ------------------------------------------------------------------
    # Laden / Speichern
    # ------------------------------------------------------------------

    async def async_load(self) -> None:
        """Lädt die gespeicherten Daten beim Start der Integration."""
        gespeicherte_daten = await self._store.async_load()
        if gespeicherte_daten:
            # Bestehende Struktur übernehmen, fehlende Schlüssel absichern
            # (z. B. falls in einer künftigen Version Felder hinzukommen).
            self._data["tasks"] = gespeicherte_daten.get("tasks", {})
            self._data["completions"] = gespeicherte_daten.get("completions", [])
            self._data["scores"] = gespeicherte_daten.get("scores", {})
            self._data["templates"] = gespeicherte_daten.get("templates", {})

        # Abwärtskompatibilität: Aufgaben, die vor Einführung der
        # Standardaufgaben-Funktion angelegt wurden, haben noch kein
        # "template_id"-Feld. Fehlt es, wird es auf None nachgetragen,
        # damit z. B. der Duplikat-Schutz beim Trigger (Vergleich auf
        # aufgabe.get("template_id")) und die Attribut-Struktur für das
        # Frontend überall konsistent sind.
        for aufgabe in self._data["tasks"].values():
            aufgabe.setdefault("template_id", None)
            # Abwärtskompatibilität: Aufgaben aus Versionen vor dem
            # Freigabe-Workflow kennen "pending_by"/"pending_since" noch
            # nicht - sie sind ja ohnehin nur im Status "pending_approval"
            # relevant, den es vorher gar nicht gab.
            aufgabe.setdefault("pending_by", None)
            aufgabe.setdefault("pending_since", None)

        # Abwärtskompatibilität: Erledigungs-Einträge aus Versionen vor
        # der nachträglichen Rücknahme-Funktion haben noch keine
        # eindeutige "completion_id" - ohne die könnte async_undo_completion()
        # den betreffenden Eintrag nicht sicher identifizieren.
        for eintrag in self._data["completions"]:
            eintrag.setdefault("completion_id", uuid.uuid4().hex)

        # Abwärtskompatibilität: Standardaufgaben, die vor Einführung des
        # Zeitplan-Triggers angelegt wurden, haben die neuen Felder noch
        # nicht - ohne Nachtrag würde _schedule_matches_today() bei jedem
        # Zugriff auf .get() zwar None liefern (und korrekt "kein
        # Zeitplan" ergeben), aber get_all_templates() im Frontend würde
        # inkonsistente Dicts liefern (mal mit, mal ohne diese Schlüssel).
        for vorlage in self._data["templates"].values():
            vorlage.setdefault("schedule_type", None)
            vorlage.setdefault("schedule_interval", None)
            vorlage.setdefault("schedule_weekday", None)
            vorlage.setdefault("schedule_anchor", None)
            vorlage.setdefault("schedule_last_triggered", None)

        _LOGGER.debug(
            "Aufgaben-Scoreboard-Daten geladen: %s Aufgabe(n), %s Standardaufgabe(n)",
            len(self._data["tasks"]),
            len(self._data["templates"]),
        )

    async def _async_persist(self) -> None:
        """Speichert den aktuellen Stand dauerhaft und informiert Zuhörer."""
        await self._store.async_save(self._data)
        # Alle Sensor-Entitäten (und darüber das Frontend) benachrichtigen,
        # dass sich Daten geändert haben, damit der Zustand aktualisiert wird.
        #
        # WICHTIG: async_dispatcher_send() darf laut Home-Assistant-Regeln
        # nur direkt aus dem Event-Loop heraus aufgerufen werden. Ruft man
        # es (auch indirekt, z. B. über den Storage-Mechanismus) aus einem
        # anderen Thread auf, stürzt die anschließende Aktualisierung der
        # Sensor-Entität (self.async_write_ha_state()) mit einem
        # RuntimeError ab - die neue Aufgabe wurde zwar gespeichert, aber
        # nie an die Oberfläche gemeldet und blieb dadurch unsichtbar.
        #
        # hass.add_job() ist die von Home Assistant empfohlene, IMMER
        # thread-sichere Methode, um eine Funktion "egal aus welchem
        # Kontext heraus" korrekt im Event-Loop auszuführen. Damit ist die
        # Aktualisierung robust, unabhängig davon, aus welchem Thread
        # _async_persist() letztlich angestoßen wird.
        self.hass.add_job(async_dispatcher_send, self.hass, SIGNAL_UPDATE)

    # ------------------------------------------------------------------
    # Aufgaben anlegen / löschen / zuweisen
    # ------------------------------------------------------------------

    async def async_add_task(
        self,
        name: str,
        description: str,
        score: int,
        assigned_to: list[str] | None = None,
        template_id: str | None = None,
    ) -> str:
        """
        Legt eine neue Aufgabe an.

        :param name: Kurzer Titel der Aufgabe.
        :param description: Ausführlichere Beschreibung (optional, kann leer sein).
        :param score: Punktzahl, die die Aufgabe bei Erledigung einbringt.
        :param assigned_to: Liste von Home-Assistant-Benutzer-IDs, denen die
            Aufgabe zugewiesen wird. Leere Liste/None = für alle Benutzer
            offen (jeder kann sie erledigen).
        :param template_id: Falls die Aufgabe aus einer Standardaufgabe
            erzeugt wurde, deren ID (sonst None). Wird für den
            Duplikat-Schutz beim automatischen Entitäts-Trigger benötigt.
        :return: Die generierte Aufgaben-ID.
        """
        task_id = uuid.uuid4().hex
        self._data["tasks"][task_id] = {
            "id": task_id,
            "name": name,
            "description": description or "",
            "score": int(score),
            "assigned_to": list(assigned_to) if assigned_to else [],
            "created_at": _jetzt_iso(),
            "status": TASK_STATUS_OPEN,
            "template_id": template_id,
            # Freigabe-Workflow: wer die Aufgabe als erledigt gemeldet hat
            # und wann - nur gesetzt, solange status == "pending_approval".
            "pending_by": None,
            "pending_since": None,
        }
        await self._async_persist()

        self.hass.add_job(
            self.hass.bus.async_fire,
            EVENT_TASK_ADDED,
            {"task_id": task_id, "name": name, "score": score},
        )
        _LOGGER.info("Neue Aufgabe angelegt: '%s' (%s Punkte)", name, score)
        return task_id

    async def async_remove_task(self, task_id: str) -> None:
        """Entfernt eine Aufgabe unwiderruflich (auch wenn sie offen ist)."""
        aufgabe = self._data["tasks"].pop(task_id, None)
        if aufgabe is None:
            _LOGGER.warning("Aufgabe mit ID '%s' existiert nicht, kann nicht entfernt werden.", task_id)
            return
        await self._async_persist()
        self.hass.add_job(self.hass.bus.async_fire, EVENT_TASK_REMOVED, {"task_id": task_id})
        _LOGGER.info("Aufgabe entfernt: '%s'", aufgabe.get("name"))

    async def async_assign_task(self, task_id: str, user_id: str) -> None:
        """Weist eine bestehende Aufgabe zusätzlich einem Benutzer zu."""
        aufgabe = self._data["tasks"].get(task_id)
        if aufgabe is None:
            _LOGGER.warning("Aufgabe '%s' nicht gefunden, Zuweisung nicht möglich.", task_id)
            return
        if user_id not in aufgabe["assigned_to"]:
            aufgabe["assigned_to"].append(user_id)
        await self._async_persist()
        self.hass.add_job(
            self.hass.bus.async_fire, EVENT_TASK_ASSIGNED, {"task_id": task_id, "user_id": user_id}
        )
        _LOGGER.info("Aufgabe '%s' wurde Benutzer '%s' zugewiesen.", aufgabe.get("name"), user_id)

    async def async_update_task(
        self,
        task_id: str,
        name: str | None = None,
        description: str | None = None,
        score: int | None = None,
        assigned_to: list[str] | None = None,
    ) -> bool:
        """
        Bearbeitet eine bestehende Aufgabe nachträglich (Titel,
        Beschreibung, Punktzahl und/oder Zuweisung). Nur die tatsächlich
        übergebenen Felder werden geändert - ein Feld, das als None
        übergeben wird (bzw. nicht in call.data enthalten ist), bleibt
        unverändert. Für "assigned_to" bedeutet das: eine LEERE Liste
        ([]) setzt die Aufgabe bewusst auf "für alle offen" zurück,
        während KEINE Angabe (None) die bisherige Zuweisung unangetastet
        lässt.

        :return: True bei Erfolg, False falls die Aufgabe nicht existiert.
        """
        aufgabe = self._data["tasks"].get(task_id)
        if aufgabe is None:
            _LOGGER.warning("Aufgabe '%s' nicht gefunden, Bearbeitung nicht möglich.", task_id)
            return False

        if name is not None:
            aufgabe["name"] = name
        if description is not None:
            aufgabe["description"] = description
        if score is not None:
            aufgabe["score"] = int(score)
        if assigned_to is not None:
            aufgabe["assigned_to"] = list(assigned_to)

        await self._async_persist()
        self.hass.add_job(self.hass.bus.async_fire, EVENT_TASK_UPDATED, {"task_id": task_id})
        _LOGGER.info("Aufgabe '%s' wurde bearbeitet.", aufgabe.get("name"))
        return True

    async def async_unassign_task(self, task_id: str, user_id: str) -> None:
        """Entfernt die Zuweisung eines Benutzers von einer Aufgabe."""
        aufgabe = self._data["tasks"].get(task_id)
        if aufgabe is None:
            _LOGGER.warning("Aufgabe '%s' nicht gefunden, Zuweisung kann nicht entfernt werden.", task_id)
            return
        if user_id in aufgabe["assigned_to"]:
            aufgabe["assigned_to"].remove(user_id)
        await self._async_persist()

    # ------------------------------------------------------------------
    # Aufgaben erledigen
    # ------------------------------------------------------------------

    async def async_complete_task(self, task_id: str, user_id: str) -> bool:
        """
        Meldet eine Aufgabe als erledigt - schreibt dabei NOCH KEINE
        Punkte gut, sondern setzt sie nur in den Zwischenstatus
        "pending_approval" (wartet auf Freigabe durch einen
        Administrator). Erst async_approve_task() vergibt tatsächlich
        Punkte. Das gilt einheitlich für alle Benutzer, auch für
        Administratoren, die selbst eine Aufgabe erledigen.

        :return: True bei Erfolg, False falls die Aufgabe nicht existiert
            oder nicht im Status "open" ist.
        """
        aufgabe = self._data["tasks"].get(task_id)
        if aufgabe is None:
            _LOGGER.warning("Aufgabe '%s' nicht gefunden, kann nicht als erledigt gemeldet werden.", task_id)
            return False
        if aufgabe["status"] != TASK_STATUS_OPEN:
            _LOGGER.warning(
                "Aufgabe '%s' hat nicht den Status 'open' (aktuell: '%s') und kann nicht "
                "als erledigt gemeldet werden.",
                aufgabe.get("name"),
                aufgabe["status"],
            )
            return False

        aufgabe["status"] = TASK_STATUS_PENDING_APPROVAL
        aufgabe["pending_by"] = user_id
        aufgabe["pending_since"] = _jetzt_iso()

        await self._async_persist()
        self.hass.add_job(
            self.hass.bus.async_fire,
            EVENT_TASK_COMPLETION_REQUESTED,
            {"task_id": task_id, "user_id": user_id},
        )
        _LOGGER.info(
            "Aufgabe '%s' wurde von Benutzer '%s' als erledigt gemeldet - wartet auf Freigabe.",
            aufgabe["name"],
            user_id,
        )
        return True

    async def async_approve_task(self, task_id: str) -> bool:
        """
        Gibt eine als erledigt gemeldete Aufgabe frei: schreibt dem
        Benutzer, der sie gemeldet hat, die Punkte gut und trägt sie in
        die Erledigungs-Historie ein. Nur für Administratoren gedacht
        (Berechtigungsprüfung erfolgt in __init__.py).

        :return: True bei Erfolg, False falls die Aufgabe nicht existiert
            oder nicht im Status "pending_approval" ist.
        """
        aufgabe = self._data["tasks"].get(task_id)
        if aufgabe is None:
            _LOGGER.warning("Aufgabe '%s' nicht gefunden, kann nicht freigegeben werden.", task_id)
            return False
        if aufgabe["status"] != TASK_STATUS_PENDING_APPROVAL:
            _LOGGER.warning(
                "Aufgabe '%s' wartet nicht auf Freigabe (aktueller Status: '%s').",
                aufgabe.get("name"),
                aufgabe["status"],
            )
            return False

        user_id = aufgabe["pending_by"]
        punkte = aufgabe["score"]

        aufgabe["status"] = TASK_STATUS_DONE
        aufgabe["pending_by"] = None
        aufgabe["pending_since"] = None

        aktueller_stand = self._data["scores"].get(user_id, 0)
        self._data["scores"][user_id] = aktueller_stand + punkte

        self._data["completions"].append(
            {
                "completion_id": uuid.uuid4().hex,
                "task_id": task_id,
                "task_name": aufgabe["name"],
                "user_id": user_id,
                "score": punkte,
                "completed_at": _jetzt_iso(),
            }
        )

        await self._async_persist()
        self.hass.add_job(
            self.hass.bus.async_fire,
            EVENT_TASK_APPROVED,
            {"task_id": task_id, "user_id": user_id, "score": punkte},
        )
        # Zusätzlich das alte Event weiterhin feuern (Abwärtskompatibilität
        # für Automationen, die von vor dem Freigabe-Workflow noch auf
        # EVENT_TASK_COMPLETED reagieren - das war bisher der Moment der
        # tatsächlichen Punktegutschrift, was jetzt hier passiert).
        self.hass.add_job(
            self.hass.bus.async_fire,
            EVENT_TASK_COMPLETED,
            {"task_id": task_id, "user_id": user_id, "score": punkte},
        )
        _LOGGER.info(
            "Aufgabe '%s' von Benutzer '%s' wurde freigegeben (+%s Punkte).",
            aufgabe["name"],
            user_id,
            punkte,
        )
        return True

    async def async_reject_task(self, task_id: str) -> bool:
        """
        Lehnt eine als erledigt gemeldete Aufgabe ab: keine Punkte,
        Aufgabe geht zurück in den Status "open" und kann erneut
        erledigt werden. Nur für Administratoren gedacht.

        :return: True bei Erfolg, False falls die Aufgabe nicht existiert
            oder nicht im Status "pending_approval" ist.
        """
        aufgabe = self._data["tasks"].get(task_id)
        if aufgabe is None:
            _LOGGER.warning("Aufgabe '%s' nicht gefunden, kann nicht abgelehnt werden.", task_id)
            return False
        if aufgabe["status"] != TASK_STATUS_PENDING_APPROVAL:
            _LOGGER.warning(
                "Aufgabe '%s' wartet nicht auf Freigabe (aktueller Status: '%s').",
                aufgabe.get("name"),
                aufgabe["status"],
            )
            return False

        abgelehnter_benutzer = aufgabe["pending_by"]
        aufgabe["status"] = TASK_STATUS_OPEN
        aufgabe["pending_by"] = None
        aufgabe["pending_since"] = None

        await self._async_persist()
        self.hass.add_job(
            self.hass.bus.async_fire,
            EVENT_TASK_REJECTED,
            {"task_id": task_id, "user_id": abgelehnter_benutzer},
        )
        _LOGGER.info(
            "Erledigungs-Meldung von Benutzer '%s' für Aufgabe '%s' wurde abgelehnt - "
            "Aufgabe ist wieder offen.",
            abgelehnter_benutzer,
            aufgabe["name"],
        )
        return True

    def _completion_ist_ruecknehmbar(self, eintrag: dict[str, Any]) -> bool:
        """
        Prüft, ob eine bereits freigegebene Erledigung noch zurückgenommen
        werden darf: BEIDE Bedingungen müssen zutreffen - innerhalb von
        UNDO_ZEITLIMIT_TAGE Tagen erledigt UND unter den letzten
        UNDO_ANZAHL_LIMIT Erledigungen desselben Benutzers.
        """
        try:
            erledigt_am = datetime.fromisoformat(eintrag["completed_at"])
        except (KeyError, ValueError):
            return False
        if datetime.now(timezone.utc) - erledigt_am > timedelta(days=UNDO_ZEITLIMIT_TAGE):
            return False

        letzte_eintraege_benutzer = sorted(
            (c for c in self._data["completions"] if c["user_id"] == eintrag["user_id"]),
            key=lambda c: c["completed_at"],
            reverse=True,
        )[:UNDO_ANZAHL_LIMIT]
        return any(c.get("completion_id") == eintrag.get("completion_id") for c in letzte_eintraege_benutzer)

    async def async_undo_completion(self, completion_id: str) -> bool:
        """
        Nimmt eine bereits freigegebene Erledigung zurück: entfernt den
        Historien-Eintrag, zieht die Punkte wieder ab und setzt die
        ursprüngliche Aufgabe (sofern sie noch existiert) zurück auf
        "open". Nur innerhalb der in _completion_ist_ruecknehmbar()
        geprüften Grenzen möglich. Nur für Administratoren gedacht.

        :return: True bei Erfolg, False falls der Eintrag nicht existiert
            oder außerhalb der Rücknahme-Grenzen liegt.
        """
        eintrag = next(
            (c for c in self._data["completions"] if c.get("completion_id") == completion_id), None
        )
        if eintrag is None:
            _LOGGER.warning("Erledigungs-Eintrag '%s' nicht gefunden, keine Rücknahme möglich.", completion_id)
            return False
        if not self._completion_ist_ruecknehmbar(eintrag):
            _LOGGER.warning(
                "Erledigung von '%s' liegt außerhalb der Rücknahme-Grenzen (%s Tage / letzte %s "
                "Einträge) - keine Rücknahme möglich.",
                eintrag.get("task_name"),
                UNDO_ZEITLIMIT_TAGE,
                UNDO_ANZAHL_LIMIT,
            )
            return False

        self._data["completions"].remove(eintrag)

        user_id = eintrag["user_id"]
        punkte = eintrag["score"]
        aktueller_stand = self._data["scores"].get(user_id, 0)
        # Nicht unter 0 fallen - falls der Punktestand zwischenzeitlich
        # z. B. durch reset_score bereits auf 0 gesetzt wurde.
        self._data["scores"][user_id] = max(0, aktueller_stand - punkte)

        # Ursprüngliche Aufgabe wieder öffnen, sofern sie noch existiert
        # (wurde sie inzwischen gelöscht, bleibt nur die Punktekorrektur).
        aufgabe = self._data["tasks"].get(eintrag["task_id"])
        if aufgabe is not None and aufgabe["status"] == TASK_STATUS_DONE:
            aufgabe["status"] = TASK_STATUS_OPEN

        await self._async_persist()
        self.hass.add_job(
            self.hass.bus.async_fire,
            EVENT_COMPLETION_UNDONE,
            {"completion_id": completion_id, "task_id": eintrag["task_id"], "user_id": user_id, "score": punkte},
        )
        _LOGGER.info(
            "Erledigung von '%s' durch Benutzer '%s' wurde zurückgenommen (-%s Punkte).",
            eintrag.get("task_name"),
            user_id,
            punkte,
        )
        return True

    async def async_reset_score(self, user_id: str) -> None:
        """
        Setzt den Punktestand eines Benutzers auf 0 zurück UND löscht
        seine komplette Erledigungs-Historie (completions) - ein
        zurückgesetzter Punktestand soll nicht neben einem weiterhin
        vorhandenen Verlauf "erledigter Aufgaben" stehen, der die alten,
        bereits gelöschten Punkte noch anzeigen würde.
        """
        self._data["scores"][user_id] = 0
        entfernte_eintraege = len(
            [c for c in self._data["completions"] if c["user_id"] == user_id]
        )
        self._data["completions"] = [c for c in self._data["completions"] if c["user_id"] != user_id]
        await self._async_persist()
        _LOGGER.info(
            "Punktestand von Benutzer '%s' wurde zurückgesetzt (inkl. %s gelöschter Verlaufs-Einträge).",
            user_id,
            entfernte_eintraege,
        )

    # ------------------------------------------------------------------
    # Standardaufgaben (Vorlagen)
    # ------------------------------------------------------------------

    async def async_add_template(
        self,
        name: str,
        description: str,
        score: int,
        assigned_to: list[str] | None = None,
        multiscoring: bool = False,
        trigger_entity_id: str | None = None,
        trigger_state: str | None = None,
        schedule_type: str | None = None,
        schedule_interval: int | None = None,
        schedule_weekday: int | None = None,
    ) -> str:
        """
        Legt eine neue Standardaufgabe (Vorlage) an.

        :param multiscoring: Bei True entsteht beim Anlegen aus dieser
            Vorlage PRO zugewiesenem Benutzer eine eigene, unabhängig
            erledigbare Aufgabe statt einer gemeinsamen.
        :param trigger_entity_id: Optionale Entität, bei deren Erreichen
            von trigger_state automatisch eine Aufgabe erzeugt wird.
        :param schedule_type: Optionaler Zeitplan-Trigger ("days" oder
            "weekly") - unabhängig vom Entitäts-Trigger nutzbar, auch
            gleichzeitig mit ihm.
        :param schedule_interval: Bei "days": alle X Tage. Bei "weekly":
            alle X Wochen (1 = jede Woche). Ohne Angabe: 1.
        :param schedule_weekday: Nur bei "weekly" erforderlich: Wochentag
            (0=Montag ... 6=Sonntag).
        :return: Die generierte Vorlagen-ID.
        """
        template_id = uuid.uuid4().hex
        schedule_type = schedule_type or None
        self._data["templates"][template_id] = {
            "id": template_id,
            "name": name,
            "description": description or "",
            "score": int(score),
            "assigned_to": list(assigned_to) if assigned_to else [],
            "multiscoring": bool(multiscoring),
            "trigger_entity_id": trigger_entity_id or None,
            "trigger_state": trigger_state or None,
            "schedule_type": schedule_type,
            "schedule_interval": (int(schedule_interval) if schedule_interval else 1) if schedule_type else None,
            "schedule_weekday": (int(schedule_weekday) if schedule_weekday is not None else None)
            if schedule_type
            else None,
            "schedule_anchor": _heute_iso() if schedule_type else None,
            "schedule_last_triggered": None,
            "created_at": _jetzt_iso(),
        }
        await self._async_persist()
        self.hass.add_job(
            self.hass.bus.async_fire, EVENT_TEMPLATE_ADDED, {"template_id": template_id, "name": name}
        )
        _LOGGER.info("Neue Standardaufgabe angelegt: '%s'", name)
        self.sync_trigger_listeners()
        if schedule_type:
            # Falls der neue Zeitplan bereits auf "heute" zutrifft, soll
            # die erste Aufgabe sofort entstehen statt erst morgen früh
            # auf die tägliche Prüfung zu warten.
            await self._async_schedule_check()
        return template_id

    async def async_update_template(
        self,
        template_id: str,
        name: str | None = None,
        description: str | None = None,
        score: int | None = None,
        assigned_to: list[str] | None = None,
        multiscoring: bool | None = None,
        trigger_entity_id: str | None = None,
        trigger_state: str | None = None,
        schedule_type: str | None = None,
        schedule_interval: int | None = None,
        schedule_weekday: int | None = None,
    ) -> bool:
        """
        Bearbeitet eine bestehende Standardaufgabe nachträglich. Nur die
        tatsächlich übergebenen Felder werden geändert (gleiches Muster
        wie async_update_task). Für trigger_entity_id/trigger_state sowie
        schedule_type gilt: ein LEERER String entfernt den jeweiligen
        Trigger bewusst, KEINE Angabe (None) lässt ihn unangetastet.

        :return: True bei Erfolg, False falls die Vorlage nicht existiert.
        """
        vorlage = self._data["templates"].get(template_id)
        if vorlage is None:
            _LOGGER.warning("Standardaufgabe '%s' nicht gefunden, Bearbeitung nicht möglich.", template_id)
            return False

        if name is not None:
            vorlage["name"] = name
        if description is not None:
            vorlage["description"] = description
        if score is not None:
            vorlage["score"] = int(score)
        if assigned_to is not None:
            vorlage["assigned_to"] = list(assigned_to)
        if multiscoring is not None:
            vorlage["multiscoring"] = bool(multiscoring)
        if trigger_entity_id is not None:
            vorlage["trigger_entity_id"] = trigger_entity_id or None
        if trigger_state is not None:
            vorlage["trigger_state"] = trigger_state or None

        if schedule_type is not None:
            if schedule_type == "":
                # Zeitplan bewusst entfernen.
                vorlage["schedule_type"] = None
                vorlage["schedule_interval"] = None
                vorlage["schedule_weekday"] = None
                vorlage["schedule_anchor"] = None
                vorlage["schedule_last_triggered"] = None
            else:
                neuer_interval = (
                    int(schedule_interval)
                    if schedule_interval is not None
                    else (vorlage.get("schedule_interval") or 1)
                )
                neuer_weekday = (
                    int(schedule_weekday) if schedule_weekday is not None else vorlage.get("schedule_weekday")
                )
                konfig_geaendert = (
                    vorlage.get("schedule_type") != schedule_type
                    or vorlage.get("schedule_interval") != neuer_interval
                    or vorlage.get("schedule_weekday") != neuer_weekday
                )
                vorlage["schedule_type"] = schedule_type
                vorlage["schedule_interval"] = neuer_interval
                vorlage["schedule_weekday"] = neuer_weekday
                if konfig_geaendert:
                    # Die Tage-/Wochen-Zählung beginnt bei geänderter
                    # Konfiguration bewusst wieder ab heute - eine alte
                    # Zähl-Referenz aus einer anderen Konfiguration wäre
                    # sonst irreführend (z. B. nach Wechsel von "alle 2
                    # Tage" auf "alle 3 Tage").
                    vorlage["schedule_anchor"] = _heute_iso()
                    vorlage["schedule_last_triggered"] = None

        await self._async_persist()
        self.hass.add_job(self.hass.bus.async_fire, EVENT_TEMPLATE_UPDATED, {"template_id": template_id})
        _LOGGER.info("Standardaufgabe '%s' wurde bearbeitet.", vorlage.get("name"))
        self.sync_trigger_listeners()
        if vorlage.get("schedule_type"):
            await self._async_schedule_check()
        return True

    async def async_remove_template(self, template_id: str) -> None:
        """Entfernt eine Standardaufgabe. Bereits daraus erzeugte Aufgaben bleiben unberührt."""
        vorlage = self._data["templates"].pop(template_id, None)
        if vorlage is None:
            _LOGGER.warning("Standardaufgabe '%s' existiert nicht, kann nicht entfernt werden.", template_id)
            return
        await self._async_persist()
        self.hass.add_job(self.hass.bus.async_fire, EVENT_TEMPLATE_REMOVED, {"template_id": template_id})
        _LOGGER.info("Standardaufgabe entfernt: '%s'", vorlage.get("name"))
        self.sync_trigger_listeners()

    async def async_create_task_from_template(self, template_id: str) -> list[str]:
        """
        Legt aus einer Standardaufgabe eine oder mehrere konkrete, offene
        Aufgaben an - manuell (Button "Jetzt anlegen") oder automatisch
        (Entitäts-Trigger, siehe _async_trigger_ausloesen()).

        Bei aktiviertem Multiscoring wird für JEDEN zugewiesenen
        Benutzer eine eigene, unabhängig erledigbare Aufgabe erzeugt
        (jede mit assigned_to=[dieser eine Benutzer]). Ohne Multiscoring
        entsteht eine einzelne Aufgabe mit der vollständigen
        Zuweisungsliste der Vorlage (wie eine normal angelegte Aufgabe).

        :return: Liste der erzeugten Aufgaben-IDs. Leer, falls die
            Vorlage nicht existiert oder Multiscoring aktiv ist, aber
            keine Benutzer zugewiesen sind (dafür gibt es dann ja keine
            Empfänger).
        """
        vorlage = self._data["templates"].get(template_id)
        if vorlage is None:
            _LOGGER.warning("Standardaufgabe '%s' nicht gefunden, Anlage nicht möglich.", template_id)
            return []

        erzeugte_ids: list[str] = []

        if vorlage["multiscoring"]:
            if not vorlage["assigned_to"]:
                _LOGGER.warning(
                    "Standardaufgabe '%s' hat Multiscoring aktiviert, aber keine "
                    "zugewiesenen Benutzer - es wurde keine Aufgabe angelegt.",
                    vorlage.get("name"),
                )
                return []
            for user_id in vorlage["assigned_to"]:
                task_id = await self.async_add_task(
                    name=vorlage["name"],
                    description=vorlage["description"],
                    score=vorlage["score"],
                    assigned_to=[user_id],
                    template_id=template_id,
                )
                erzeugte_ids.append(task_id)
        else:
            task_id = await self.async_add_task(
                name=vorlage["name"],
                description=vorlage["description"],
                score=vorlage["score"],
                assigned_to=vorlage["assigned_to"],
                template_id=template_id,
            )
            erzeugte_ids.append(task_id)

        _LOGGER.info(
            "%s Aufgabe(n) aus Standardaufgabe '%s' angelegt.", len(erzeugte_ids), vorlage.get("name")
        )
        return erzeugte_ids

    def _template_has_open_tasks(self, template_id: str) -> bool:
        """
        Prüft, ob aus dieser Vorlage noch mindestens eine "aktive" Aufgabe
        existiert (Duplikat-Schutz). "Aktiv" bedeutet hier: offen ODER
        bereits als erledigt gemeldet, aber noch nicht freigegeben - eine
        gemeldete, aber unbestätigte Aufgabe soll nicht durch einen
        erneuten Trigger/Zeitplan-Check dupliziert werden.
        """
        return any(
            aufgabe.get("template_id") == template_id
            and aufgabe["status"] in (TASK_STATUS_OPEN, TASK_STATUS_PENDING_APPROVAL)
            for aufgabe in self._data["tasks"].values()
        )

    @callback
    def sync_trigger_listeners(self) -> None:
        """
        Gleicht die abonnierten Entitäts-Trigger mit dem aktuellen Stand
        der Standardaufgaben ab: alle bisherigen Listener werden
        abgemeldet und aus den aktuellen Vorlagen (die einen
        trigger_entity_id + trigger_state gesetzt haben) neu abonniert.

        Wird aufgerufen: einmalig beim Start der Integration (aus
        __init__.py, nach async_load()) sowie nach jedem
        Anlegen/Bearbeiten/Löschen einer Standardaufgabe. Bei der zu
        erwartenden geringen Anzahl an Standardaufgaben ist der
        "alles abmelden und neu aufbauen"-Ansatz einfacher und robuster
        als einen Diff zu berechnen.
        """
        for abmelden in self._trigger_unsub.values():
            abmelden()
        self._trigger_unsub.clear()

        for vorlage in self._data["templates"].values():
            entity_id = vorlage.get("trigger_entity_id")
            ziel_zustand = vorlage.get("trigger_state")
            if not entity_id or not ziel_zustand:
                continue
            template_id = vorlage["id"]
            self._trigger_unsub[template_id] = async_track_state_change_event(
                self.hass,
                [entity_id],
                self._erzeuge_trigger_callback(template_id, ziel_zustand),
            )

    def _erzeuge_trigger_callback(self, template_id: str, ziel_zustand: str):
        """
        Baut den Event-Callback für einen einzelnen Entitäts-Trigger.
        Eigene Funktion (statt Inline-Closure in sync_trigger_listeners),
        damit template_id/ziel_zustand pro Vorlage korrekt "eingefangen"
        werden und nicht durch die Schleifenvariable überschrieben
        werden können.
        """

        @callback
        def _callback(event) -> None:
            neuer_zustand = event.data.get("new_state")
            alter_zustand = event.data.get("old_state")
            if neuer_zustand is None or neuer_zustand.state != ziel_zustand:
                return
            # Nur bei einer echten FLANKE auslösen (Übergang IN den
            # Zielzustand hinein) - async_track_state_change_event feuert
            # bei JEDER Zustandsänderung der Entität, auch bei reinen
            # Attribut-Änderungen während der Zustand bereits dem
            # Zielwert entspricht. Ohne diese Prüfung würde z. B. jede
            # Attribut-Aktualisierung eines bereits "on" stehenden
            # Sensors erneut eine Aufgabe erzeugen wollen.
            if alter_zustand is not None and alter_zustand.state == ziel_zustand:
                return
            self.hass.async_create_task(self._async_trigger_ausloesen(template_id))

        return _callback

    async def _async_trigger_ausloesen(self, template_id: str) -> None:
        """Wird bei einer Trigger-Flanke aufgerufen; legt (Duplikat-geschützt) eine neue Aufgabe an."""
        if self._template_has_open_tasks(template_id):
            _LOGGER.debug(
                "Entitäts-Trigger für Standardaufgabe '%s' hat ausgelöst, es existiert "
                "aber noch eine offene Aufgabe daraus - es wird nichts Neues angelegt.",
                template_id,
            )
            return
        await self.async_create_task_from_template(template_id)

    # ------------------------------------------------------------------
    # Zeitplan-Trigger (alle X Tage / jede bzw. alle X Wochen am
    # Wochentag Y) - unabhängig vom Entitäts-Trigger nutzbar, auch
    # gleichzeitig mit ihm.
    # ------------------------------------------------------------------

    @callback
    def async_setup_schedule(self) -> None:
        """
        Registriert die tägliche Zeitplan-Prüfung (einmal um 00:05 Uhr
        Server-Zeit). Wird einmalig beim Start der Integration aus
        __init__.py aufgerufen, direkt nach async_load().

        Zusätzlich wird sofort eine einmalige Nachhol-Prüfung angestoßen:
        War Home Assistant um 00:05 Uhr nicht aktiv (z. B. Neustart am
        Morgen), würde ohne diese Nachhol-Prüfung ein fälliger Zeitplan
        erst am nächsten Tag bemerkt.
        """
        if self._schedule_unsub is not None:
            return
        self._schedule_unsub = async_track_time_change(
            self.hass, self._schedule_time_callback, hour=0, minute=5, second=0
        )
        self.hass.async_create_task(self._async_schedule_check())

    @callback
    def _schedule_time_callback(self, jetzt) -> None:
        """Callback von async_track_time_change - stößt die eigentliche (async) Prüfung an."""
        self.hass.async_create_task(self._async_schedule_check(jetzt))

    async def _async_schedule_check(self, jetzt=None) -> None:
        """
        Prüft für alle Standardaufgaben mit konfiguriertem Zeitplan, ob
        heute ein fälliger Tag ist, und legt bei Bedarf (Duplikat-Schutz-
        geprüft) eine neue Aufgabe an.

        Zwei voneinander unabhängige Schutzmechanismen verhindern
        doppelte Anlage:
          1. schedule_last_triggered == heute: verhindert eine zweite
             Anlage am selben Tag, selbst wenn die zuvor erzeugte
             Aufgabe zwischenzeitlich bereits erledigt wurde (die
             "offene Aufgabe existiert bereits"-Prüfung allein würde das
             nicht abdecken).
          2. _template_has_open_tasks(): das bestehende, vom
             Entitäts-Trigger bekannte Duplikat-Schutz-Muster - keine
             neue Aufgabe, solange aus dieser Vorlage noch eine offene
             existiert.
        """
        heute = (jetzt or dt_util.now()).date()
        heute_iso = heute.isoformat()

        for vorlage in list(self._data["templates"].values()):
            if not vorlage.get("schedule_type"):
                continue
            if vorlage.get("schedule_last_triggered") == heute_iso:
                continue
            if not self._schedule_matches_today(vorlage, heute):
                continue
            if self._template_has_open_tasks(vorlage["id"]):
                continue

            vorlage["schedule_last_triggered"] = heute_iso
            await self._async_persist()
            _LOGGER.info(
                "Zeitplan-Trigger für Standardaufgabe '%s' ist heute fällig - lege Aufgabe an.",
                vorlage.get("name"),
            )
            await self.async_create_task_from_template(vorlage["id"])

    @staticmethod
    def _schedule_matches_today(vorlage: dict[str, Any], heute: date) -> bool:
        """
        Prüft, ob der Zeitplan einer Vorlage auf das übergebene Datum
        zutrifft.

        - "days": zutreffend, wenn die Anzahl Tage seit schedule_anchor
          ein ganzzahliges Vielfaches von schedule_interval ist.
        - "weekly": zutreffend, wenn heute der konfigurierte Wochentag
          ist UND die Anzahl KALENDERWOCHEN seit der Woche von
          schedule_anchor ein ganzzahliges Vielfaches von
          schedule_interval ist (schedule_interval=1 entspricht damit
          "jede Woche").
        """
        schedule_type = vorlage.get("schedule_type")
        if not schedule_type:
            return False

        intervall = max(1, int(vorlage.get("schedule_interval") or 1))
        anchor_str = vorlage.get("schedule_anchor")
        anchor = date.fromisoformat(anchor_str) if anchor_str else heute
        if heute < anchor:
            return False

        if schedule_type == SCHEDULE_TYPE_DAYS:
            return (heute - anchor).days % intervall == 0

        if schedule_type == SCHEDULE_TYPE_WEEKLY:
            ziel_wochentag = vorlage.get("schedule_weekday")
            if ziel_wochentag is None or heute.weekday() != int(ziel_wochentag):
                return False
            anchor_montag = anchor - timedelta(days=anchor.weekday())
            heute_montag = heute - timedelta(days=heute.weekday())
            wochen_diff = (heute_montag - anchor_montag).days // 7
            return wochen_diff % intervall == 0

        return False

    def async_unload(self) -> None:
        """Meldet alle Entitäts- und Zeitplan-Trigger-Listener ab (beim Entladen/Neuladen der Integration)."""
        for abmelden in self._trigger_unsub.values():
            abmelden()
        self._trigger_unsub.clear()
        if self._schedule_unsub is not None:
            self._schedule_unsub()
            self._schedule_unsub = None

    # ------------------------------------------------------------------
    # Lesezugriffe (werden u. a. von den Sensor-Entitäten verwendet)
    # ------------------------------------------------------------------

    def get_score(self, user_id: str) -> int:
        """Gibt den aktuellen Punktestand eines Benutzers zurück."""
        return int(self._data["scores"].get(user_id, 0))

    def get_open_tasks_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """
        Liefert alle offenen Aufgaben, die für den angegebenen Benutzer
        sichtbar/erledigbar sind: entweder ihm explizit zugewiesen ODER
        für alle Benutzer freigegeben (assigned_to ist leer).

        WICHTIG: Es werden bewusst KOPIEN der internen Aufgaben-Dicts
        zurückgegeben (siehe Kommentar bei get_all_tasks()) - sonst
        entdeckt Home Assistant nachträgliche Bearbeitungen (z. B. über
        async_update_task) nicht zuverlässig.
        """
        ergebnis = []
        for aufgabe in self._data["tasks"].values():
            if aufgabe["status"] != TASK_STATUS_OPEN:
                continue
            zugewiesen = aufgabe["assigned_to"]
            if not zugewiesen or user_id in zugewiesen:
                ergebnis.append(copy.deepcopy(aufgabe))
        return ergebnis

    def get_pending_tasks_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """
        Liefert die Aufgaben, die DIESER Benutzer selbst als erledigt
        gemeldet hat und die noch auf Freigabe warten (für die Anzeige
        "wartet auf Freigabe" im persönlichen Bereich).
        """
        return [
            copy.deepcopy(a)
            for a in self._data["tasks"].values()
            if a["status"] == TASK_STATUS_PENDING_APPROVAL and a.get("pending_by") == user_id
        ]

    def get_all_pending_tasks(self) -> list[dict[str, Any]]:
        """Liefert ALLE auf Freigabe wartenden Aufgaben (für den Admin-Bereich)."""
        return [
            copy.deepcopy(a) for a in self._data["tasks"].values() if a["status"] == TASK_STATUS_PENDING_APPROVAL
        ]

    def get_completed_tasks_for_user(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """
        Liefert die letzten erledigten (freigegebenen) Aufgaben eines
        Benutzers (neueste zuerst). Jeder Eintrag bekommt zusätzlich ein
        vom Server berechnetes "ruecknehmbar"-Flag - so muss dieselbe
        Grenzwert-Logik (Zeit + Anzahl) nicht zusätzlich im Frontend
        nachgebaut werden; einzige Quelle der Wahrheit bleibt
        _completion_ist_ruecknehmbar().
        """
        eintraege = [copy.deepcopy(c) for c in self._data["completions"] if c["user_id"] == user_id]
        eintraege.sort(key=lambda c: c["completed_at"], reverse=True)
        eintraege = eintraege[:limit]
        for eintrag in eintraege:
            eintrag["ruecknehmbar"] = self._completion_ist_ruecknehmbar(eintrag)
        return eintraege

    def get_all_open_tasks(self) -> list[dict[str, Any]]:
        """Liefert alle offenen Aufgaben (für Übersichts-/Admin-Ansicht)."""
        return [copy.deepcopy(a) for a in self._data["tasks"].values() if a["status"] == TASK_STATUS_OPEN]

    def get_all_tasks(self) -> list[dict[str, Any]]:
        """
        Liefert wirklich alle Aufgaben, unabhängig vom Status.

        WICHTIG - Kopien statt Referenzen:
        Diese Methode speist u. a. das "alle_aufgaben"-Attribut des
        Übersichts-Sensors, das Home Assistant bei jedem
        async_write_ha_state() mit dem zuvor gespeicherten Zustand
        vergleicht (old_state.attributes == neue_attribute), um zu
        entscheiden, ob überhaupt ein state_changed-Event gefeuert wird.
        Aufgaben werden in diesem Manager bewusst IN PLACE verändert
        (z. B. async_update_task() setzt aufgabe["name"] = ... direkt
        auf dem bestehenden Dict). Würden hier die Original-Dict-
        Objekte zurückgegeben, würde eine spätere Bearbeitung
        rückwirkend auch den bereits an HA übergebenen alten
        Attribut-Snapshot "mit verändern" (Python hält Dicts per
        Referenz) - der Gleichheitsvergleich sähe dann fälschlich
        KEINEN Unterschied, HA würde kein Event feuern, und die
        Bearbeitung bliebe im Frontend unsichtbar, bis sich zufällig
        etwas anderes (z. B. die Aufgabenzahl durch add_task) ändert.
        Mit copy.deepcopy() ist jeder zurückgegebene Snapshot
        unabhängig von zukünftigen Mutationen der internen Daten.
        """
        return [copy.deepcopy(a) for a in self._data["tasks"].values()]

    def get_all_templates(self) -> list[dict[str, Any]]:
        """Liefert alle Standardaufgaben (für die Admin-Ansicht im Panel). Kopien aus denselben Gründen wie get_all_tasks()."""
        return [copy.deepcopy(v) for v in self._data["templates"].values()]
