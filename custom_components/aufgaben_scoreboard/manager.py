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
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    EVENT_TASK_ADDED,
    EVENT_TASK_ASSIGNED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_REMOVED,
    EVENT_TASK_UPDATED,
    EVENT_TEMPLATE_ADDED,
    EVENT_TEMPLATE_REMOVED,
    EVENT_TEMPLATE_UPDATED,
    SIGNAL_UPDATE,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def _jetzt_iso() -> str:
    """Gibt den aktuellen Zeitpunkt als ISO-8601-String (UTC) zurück."""
    return datetime.now(timezone.utc).isoformat()


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
            "status": "open",
            "template_id": template_id,
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
        Markiert eine Aufgabe als erledigt und schreibt dem Benutzer die
        Punkte gut.

        :return: True bei Erfolg, False falls die Aufgabe nicht existiert
            oder bereits erledigt wurde.
        """
        aufgabe = self._data["tasks"].get(task_id)
        if aufgabe is None:
            _LOGGER.warning("Aufgabe '%s' nicht gefunden, kann nicht erledigt werden.", task_id)
            return False
        if aufgabe["status"] == "done":
            _LOGGER.warning("Aufgabe '%s' wurde bereits erledigt.", aufgabe.get("name"))
            return False

        aufgabe["status"] = "done"
        punkte = aufgabe["score"]

        # Punktestand des Benutzers erhöhen.
        aktueller_stand = self._data["scores"].get(user_id, 0)
        self._data["scores"][user_id] = aktueller_stand + punkte

        # Im Verlauf (Historie) vermerken.
        self._data["completions"].append(
            {
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
            EVENT_TASK_COMPLETED,
            {"task_id": task_id, "user_id": user_id, "score": punkte},
        )
        _LOGGER.info(
            "Aufgabe '%s' wurde von Benutzer '%s' erledigt (+%s Punkte).",
            aufgabe["name"],
            user_id,
            punkte,
        )
        return True

    async def async_reset_score(self, user_id: str) -> None:
        """Setzt den Punktestand eines Benutzers auf 0 zurück."""
        self._data["scores"][user_id] = 0
        await self._async_persist()
        _LOGGER.info("Punktestand von Benutzer '%s' wurde zurückgesetzt.", user_id)

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
    ) -> str:
        """
        Legt eine neue Standardaufgabe (Vorlage) an.

        :param multiscoring: Bei True entsteht beim Anlegen aus dieser
            Vorlage PRO zugewiesenem Benutzer eine eigene, unabhängig
            erledigbare Aufgabe statt einer gemeinsamen.
        :param trigger_entity_id: Optionale Entität, bei deren Erreichen
            von trigger_state automatisch eine Aufgabe erzeugt wird.
        :return: Die generierte Vorlagen-ID.
        """
        template_id = uuid.uuid4().hex
        self._data["templates"][template_id] = {
            "id": template_id,
            "name": name,
            "description": description or "",
            "score": int(score),
            "assigned_to": list(assigned_to) if assigned_to else [],
            "multiscoring": bool(multiscoring),
            "trigger_entity_id": trigger_entity_id or None,
            "trigger_state": trigger_state or None,
            "created_at": _jetzt_iso(),
        }
        await self._async_persist()
        self.hass.add_job(
            self.hass.bus.async_fire, EVENT_TEMPLATE_ADDED, {"template_id": template_id, "name": name}
        )
        _LOGGER.info("Neue Standardaufgabe angelegt: '%s'", name)
        self.sync_trigger_listeners()
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
    ) -> bool:
        """
        Bearbeitet eine bestehende Standardaufgabe nachträglich. Nur die
        tatsächlich übergebenen Felder werden geändert (gleiches Muster
        wie async_update_task). Für trigger_entity_id/trigger_state gilt:
        ein LEERER String entfernt den Trigger bewusst, KEINE Angabe
        (None) lässt ihn unangetastet.

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

        await self._async_persist()
        self.hass.add_job(self.hass.bus.async_fire, EVENT_TEMPLATE_UPDATED, {"template_id": template_id})
        _LOGGER.info("Standardaufgabe '%s' wurde bearbeitet.", vorlage.get("name"))
        self.sync_trigger_listeners()
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
        """Prüft, ob aus dieser Vorlage noch mindestens eine offene Aufgabe existiert (Duplikat-Schutz)."""
        return any(
            aufgabe.get("template_id") == template_id and aufgabe["status"] == "open"
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

    def async_unload(self) -> None:
        """Meldet alle Entitäts-Trigger-Listener ab (beim Entladen/Neuladen der Integration)."""
        for abmelden in self._trigger_unsub.values():
            abmelden()
        self._trigger_unsub.clear()

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
            if aufgabe["status"] != "open":
                continue
            zugewiesen = aufgabe["assigned_to"]
            if not zugewiesen or user_id in zugewiesen:
                ergebnis.append(copy.deepcopy(aufgabe))
        return ergebnis

    def get_completed_tasks_for_user(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Liefert die letzten erledigten Aufgaben eines Benutzers (neueste zuerst)."""
        eintraege = [copy.deepcopy(c) for c in self._data["completions"] if c["user_id"] == user_id]
        eintraege.sort(key=lambda c: c["completed_at"], reverse=True)
        return eintraege[:limit]

    def get_all_open_tasks(self) -> list[dict[str, Any]]:
        """Liefert alle offenen Aufgaben (für Übersichts-/Admin-Ansicht)."""
        return [copy.deepcopy(a) for a in self._data["tasks"].values() if a["status"] == "open"]

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
