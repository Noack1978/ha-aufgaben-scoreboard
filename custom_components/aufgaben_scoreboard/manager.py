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

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    EVENT_TASK_ADDED,
    EVENT_TASK_ASSIGNED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_REMOVED,
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
    }
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = {
            "tasks": {},
            "completions": [],
            "scores": {},
        }

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
        _LOGGER.debug("Aufgaben-Scoreboard-Daten geladen: %s Aufgabe(n)", len(self._data["tasks"]))

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
    ) -> str:
        """
        Legt eine neue Aufgabe an.

        :param name: Kurzer Titel der Aufgabe.
        :param description: Ausführlichere Beschreibung (optional, kann leer sein).
        :param score: Punktzahl, die die Aufgabe bei Erledigung einbringt.
        :param assigned_to: Liste von Home-Assistant-Benutzer-IDs, denen die
            Aufgabe zugewiesen wird. Leere Liste/None = für alle Benutzer
            offen (jeder kann sie erledigen).
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
        """
        ergebnis = []
        for aufgabe in self._data["tasks"].values():
            if aufgabe["status"] != "open":
                continue
            zugewiesen = aufgabe["assigned_to"]
            if not zugewiesen or user_id in zugewiesen:
                ergebnis.append(aufgabe)
        return ergebnis

    def get_completed_tasks_for_user(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Liefert die letzten erledigten Aufgaben eines Benutzers (neueste zuerst)."""
        eintraege = [c for c in self._data["completions"] if c["user_id"] == user_id]
        eintraege.sort(key=lambda c: c["completed_at"], reverse=True)
        return eintraege[:limit]

    def get_all_open_tasks(self) -> list[dict[str, Any]]:
        """Liefert alle offenen Aufgaben (für Übersichts-/Admin-Ansicht)."""
        return [a for a in self._data["tasks"].values() if a["status"] == "open"]

    def get_all_tasks(self) -> list[dict[str, Any]]:
        """Liefert wirklich alle Aufgaben, unabhängig vom Status."""
        return list(self._data["tasks"].values())
