"""
Konstanten für die Integration "Aufgaben-Punktesystem" (aufgaben_scoreboard).

Diese Datei bündelt alle festen Werte (Domain-Name, Service-Namen,
Attribut-Schlüssel, Signalnamen etc.), damit sie an einer zentralen
Stelle gepflegt und in allen Modulen der Integration konsistent
verwendet werden können.
"""

from __future__ import annotations

# -----------------------------------------------------------------------
# Grundlegende Integration-Konstanten
# -----------------------------------------------------------------------

# Eindeutiger technischer Name der Integration (muss mit dem Ordnernamen
# unter custom_components/ übereinstimmen).
DOMAIN = "aufgaben_scoreboard"

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

EVENT_TEMPLATE_ADDED = f"{DOMAIN}_template_added"
EVENT_TEMPLATE_UPDATED = f"{DOMAIN}_template_updated"
EVENT_TEMPLATE_REMOVED = f"{DOMAIN}_template_removed"

# -----------------------------------------------------------------------
# Service-Namen (aufrufbar z. B. in Automationen/Skripten sowie über die
# mitgelieferte Sidebar/Custom Card).
# -----------------------------------------------------------------------

SERVICE_ADD_TASK = "add_task"
SERVICE_UPDATE_TASK = "update_task"
SERVICE_REMOVE_TASK = "remove_task"
SERVICE_ASSIGN_TASK = "assign_task"
SERVICE_UNASSIGN_TASK = "unassign_task"
SERVICE_COMPLETE_TASK = "complete_task"
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
# Konstanten für das Frontend (Sidebar-Panel + Custom Card).
# -----------------------------------------------------------------------

# Pfad, unter dem die JavaScript-Dateien der Integration im Browser
# erreichbar sind (wird per hass.http.async_register_static_paths
# registriert).
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
