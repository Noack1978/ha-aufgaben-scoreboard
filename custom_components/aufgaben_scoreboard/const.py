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
EVENT_TASK_COMPLETED = f"{DOMAIN}_task_completed"
EVENT_TASK_REMOVED = f"{DOMAIN}_task_removed"
EVENT_TASK_ASSIGNED = f"{DOMAIN}_task_assigned"

# -----------------------------------------------------------------------
# Service-Namen (aufrufbar z. B. in Automationen/Skripten sowie über die
# mitgelieferte Sidebar/Custom Card).
# -----------------------------------------------------------------------

SERVICE_ADD_TASK = "add_task"
SERVICE_REMOVE_TASK = "remove_task"
SERVICE_ASSIGN_TASK = "assign_task"
SERVICE_UNASSIGN_TASK = "unassign_task"
SERVICE_COMPLETE_TASK = "complete_task"
SERVICE_RESET_SCORE = "reset_score"

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
