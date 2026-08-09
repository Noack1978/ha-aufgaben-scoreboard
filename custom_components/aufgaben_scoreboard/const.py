"""
Konstanten für die Integration "Aufgaben-Punktesystem" (aufgaben_scoreboard).

Diese Datei bündelt alle festen Werte (Domain-Name, Service-Namen,
Attribut-Schlüssel, Signalnamen etc.), damit sie an einer zentralen
Stelle gepflegt und in allen Modulen der Integration konsistent
verwendet werden können.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

# -----------------------------------------------------------------------
# Grundlegende Integration-Konstanten
# -----------------------------------------------------------------------

# Eindeutiger technischer Name der Integration (muss mit dem Ordnernamen
# unter custom_components/ übereinstimmen).
DOMAIN = "aufgaben_scoreboard"

# Version aus manifest.json auslesen - wird als Cache-Busting-Parameter
# (?v=...) an die Frontend-Ressourcen-URL der Custom Card angehängt, damit
# Browser nach einem Update zuverlässig die neue Datei laden statt einer
# alten, gecachten Version (siehe _async_register_card() in __init__.py).
_MANIFEST_PFAD = Path(__file__).parent / "manifest.json"
try:
    with open(_MANIFEST_PFAD, encoding="utf-8") as _manifest_datei:
        INTEGRATION_VERSION: Final[str] = json.load(_manifest_datei).get("version", "0.0.0")
except (OSError, ValueError):
    INTEGRATION_VERSION = "0.0.0"

# Von dieser Integration bereitgestellte Plattformen (hier: nur Sensoren,
# ein Sensor pro Home-Assistant-Benutzer mit dessen Punktestand).
PLATFORMS = ["sensor"]

# -----------------------------------------------------------------------
# Speicherung (Home Assistant "Store"-Helper, JSON-Datei in .storage/)
# -----------------------------------------------------------------------

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_data"

# -----------------------------------------------------------------------
# Signal für die interne Kommunikation (Dispatcher).
# Wird gesendet, sobald sich Aufgaben oder Punktestände ändern, damit die
# Sensor-Entitäten ihren Zustand aktualisieren können.
# -----------------------------------------------------------------------

SIGNAL_UPDATE = f"{DOMAIN}_update"

# -----------------------------------------------------------------------
# Von Home Assistant ausgelöste Events (z. B. für Automationen nutzbar,
# etwa um bei Aufgaben-Erledigung eine Benachrichtigung zu senden).
# -----------------------------------------------------------------------

EVENT_TASK_ADDED = f"{DOMAIN}_task_added"
EVENT_TASK_UPDATED = f"{DOMAIN}_task_updated"
EVENT_TASK_COMPLETED = f"{DOMAIN}_task_completed"
EVENT_TASK_REMOVED = f"{DOMAIN}_task_removed"
EVENT_TASK_ASSIGNED = f"{DOMAIN}_task_assigned"

# Freigabe-Workflow: Erledigung durch einen Benutzer erzeugt zunächst nur
# eine ANFRAGE (pending_approval) - erst nach Admin-Freigabe werden
# Punkte gutgeschrieben. Siehe manager.py für die Statuslogik.
EVENT_TASK_COMPLETION_REQUESTED = f"{DOMAIN}_task_completion_requested"
EVENT_TASK_APPROVED = f"{DOMAIN}_task_approved"
EVENT_TASK_REJECTED = f"{DOMAIN}_task_rejected"
EVENT_COMPLETION_UNDONE = f"{DOMAIN}_completion_undone"

EVENT_TEMPLATE_ADDED = f"{DOMAIN}_template_added"
EVENT_TEMPLATE_UPDATED = f"{DOMAIN}_template_updated"
EVENT_TEMPLATE_REMOVED = f"{DOMAIN}_template_removed"

# -----------------------------------------------------------------------
# Service-Namen (aufrufbar z. B. in Automationen/Skripten sowie über das
# mitgelieferte Sidebar-Panel).
# -----------------------------------------------------------------------

SERVICE_ADD_TASK = "add_task"
SERVICE_UPDATE_TASK = "update_task"
SERVICE_REMOVE_TASK = "remove_task"
SERVICE_ASSIGN_TASK = "assign_task"
SERVICE_UNASSIGN_TASK = "unassign_task"
SERVICE_COMPLETE_TASK = "complete_task"
SERVICE_APPROVE_TASK = "approve_task"
SERVICE_REJECT_TASK = "reject_task"
SERVICE_UNDO_COMPLETION = "undo_completion"
SERVICE_RESET_SCORE = "reset_score"

# Standardaufgaben (Vorlagen): wiederverwendbare Aufgaben-Definitionen,
# aus denen manuell (Button "Jetzt anlegen") oder automatisch (per
# Entitäts-Trigger) konkrete Aufgaben erzeugt werden können.
SERVICE_ADD_TEMPLATE = "add_template"
SERVICE_UPDATE_TEMPLATE = "update_template"
SERVICE_REMOVE_TEMPLATE = "remove_template"
SERVICE_CREATE_TASK_FROM_TEMPLATE = "create_task_from_template"

# -----------------------------------------------------------------------
# Attribut-/Feld-Schlüssel, die sowohl in Service-Aufrufen als auch in
# den Attributen der Sensor-Entitäten verwendet werden.
# -----------------------------------------------------------------------

ATTR_TASK_ID = "task_id"
ATTR_NAME = "name"
ATTR_DESCRIPTION = "description"
ATTR_SCORE = "score"
ATTR_USER_ID = "user_id"
ATTR_ASSIGNED_TO = "assigned_to"
ATTR_COMPLETION_ID = "completion_id"

# -----------------------------------------------------------------------
# Freigabe-Workflow (Erledigung -> Prüfung durch Admin -> Punkte)
# -----------------------------------------------------------------------

# Aufgaben-Status-Werte (bisher nur "open"/"done" - neu dazwischen:
# "pending_approval", solange ein Benutzer die Aufgabe als erledigt
# gemeldet hat, ein Admin sie aber noch nicht bestätigt hat).
TASK_STATUS_OPEN = "open"
TASK_STATUS_PENDING_APPROVAL = "pending_approval"
TASK_STATUS_DONE = "done"

# Nachträgliche Rücknahme einer bereits freigegebenen Erledigung: nur
# innerhalb dieses Zeitraums UND nur unter den letzten N Erledigungen
# DESSELBEN Benutzers möglich (beide Bedingungen müssen zutreffen).
UNDO_ZEITLIMIT_TAGE = 7
UNDO_ANZAHL_LIMIT = 20

# Standardaufgaben (Vorlagen)
ATTR_TEMPLATE_ID = "template_id"
ATTR_MULTISCORING = "multiscoring"
ATTR_TRIGGER_ENTITY_ID = "trigger_entity_id"
ATTR_TRIGGER_STATE = "trigger_state"

# Zeitplan-Trigger für Standardaufgaben (zusätzlich/alternativ zum
# Entitäts-Trigger): automatische Anlage nach Tages- oder
# Wochen-Intervall, siehe AufgabenScoreboardManager._schedule_matches_today().
ATTR_SCHEDULE_TYPE = "schedule_type"
ATTR_SCHEDULE_INTERVAL = "schedule_interval"
ATTR_SCHEDULE_WEEKDAY = "schedule_weekday"

SCHEDULE_TYPE_DAYS = "days"
SCHEDULE_TYPE_WEEKLY = "weekly"

# -----------------------------------------------------------------------
# Konstanten für das Frontend (Sidebar-Panel).
# -----------------------------------------------------------------------

# Pfad, unter dem die JavaScript-Datei des Panels im Browser erreichbar
# ist (wird per hass.http.async_register_static_paths registriert).
FRONTEND_URL_BASE = f"/{DOMAIN}_frontend"

PANEL_JS_FILENAME = "aufgaben-scoreboard-panel.js"
CARD_JS_FILENAME = "aufgaben-scoreboard-card.js"

# URL-Pfad, unter dem das Panel in der Seitenleiste erscheint
# (https://<ha-instanz>/aufgaben-scoreboard).
PANEL_URL_PATH = "aufgaben-scoreboard"
PANEL_TITLE = "Aufgaben"
PANEL_ICON = "mdi:star-check-outline"

# Präfix, mit dem alle vom Sensor-Plattform erzeugten Entitäten
# (ein Sensor pro Benutzer) eindeutig benannt werden.
USER_SENSOR_UNIQUE_ID_PREFIX = f"{DOMAIN}_user_"

# Unique-ID der globalen Sensor-Entität, die ALLE offenen Aufgaben
# (unabhängig vom Benutzer) als Attribut bereitstellt. Wird u. a. vom
# Sidebar-Panel für die Admin-/Übersichtsansicht verwendet.
ALL_TASKS_SENSOR_UNIQUE_ID = f"{DOMAIN}_alle_offenen_aufgaben"

# -----------------------------------------------------------------------
# Options-Flow: Auswahl, welche Home-Assistant-Benutzer von dieser
# Integration berücksichtigt werden (eigener Punkte-Sensor + in
# Zuweisungslisten wählbar). Damit lassen sich z. B. technische
# Benutzer/Integrations-Accounts, die zwar aktiv aber keine "echten"
# Haushaltsmitglieder sind, gezielt ausblenden.
# -----------------------------------------------------------------------

OPTION_ENABLED_USERS = "enabled_users"
