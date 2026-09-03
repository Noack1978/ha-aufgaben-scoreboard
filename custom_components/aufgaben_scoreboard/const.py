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

# Siegerehrung: ermittelt den/die Benutzer mit dem höchsten Punktestand,
# erhöht deren Sieg-Zähler, schreibt bei aktiviertem Prämien-System die
# Punktestände aufs Punktekonto gut und setzt danach ALLE Punktestände
# gleichzeitig zurück (neue Runde beginnt).
EVENT_SIEGERERUNG_DURCHGEFUEHRT = f"{DOMAIN}_siegerehrung_durchgefuehrt"

# Prämien-System (optional per Options-Flow aktivierbar): Punktekonto,
# das bei der Siegerehrung gespeist wird, und Prämien, die gegen
# gesammeltes Guthaben eingelöst werden können (Freigabe-Workflow analog
# zu Aufgaben-Erledigungen).
EVENT_REWARD_REDEMPTION_REQUESTED = f"{DOMAIN}_reward_redemption_requested"
EVENT_REWARD_REDEMPTION_APPROVED = f"{DOMAIN}_reward_redemption_approved"
EVENT_REWARD_REDEMPTION_REJECTED = f"{DOMAIN}_reward_redemption_rejected"

# Fälligkeit / Erinnerung: EVENT_TASK_OVERDUE feuert einmalig, sobald
# eine Aufgabe ihr Fälligkeitsdatum erreicht/überschreitet.
# EVENT_TASK_REMINDER feuert einmalig, sobald eine Aufgabe seit der
# konfigurierten Anzahl Tage ununterbrochen offen ist - unabhängig von
# einer eventuell zusätzlich gesetzten Fälligkeit, beide können
# gleichzeitig an derselben Aufgabe konfiguriert sein.
EVENT_TASK_OVERDUE = f"{DOMAIN}_task_overdue"
EVENT_TASK_REMINDER = f"{DOMAIN}_task_reminder"

# Manueller Punktabzug durch einen Administrator, unabhängig von Aufgaben.
EVENT_POINTS_DEDUCTED = f"{DOMAIN}_points_deducted"

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
SERVICE_DEDUCT_POINTS = "deduct_points"
SERVICE_RESET_SCORE = "reset_score"

# Standardaufgaben (Vorlagen): wiederverwendbare Aufgaben-Definitionen,
# aus denen manuell (Button "Jetzt anlegen") oder automatisch (per
# Entitäts-Trigger) konkrete Aufgaben erzeugt werden können.
SERVICE_ADD_TEMPLATE = "add_template"
SERVICE_UPDATE_TEMPLATE = "update_template"
SERVICE_REMOVE_TEMPLATE = "remove_template"
SERVICE_CREATE_TASK_FROM_TEMPLATE = "create_task_from_template"

# Siegerehrung
SERVICE_PERFORM_AWARDS = "perform_awards"
SERVICE_RESET_WINS = "reset_wins"

# Prämien-System
SERVICE_ADD_REWARD = "add_reward"
SERVICE_UPDATE_REWARD = "update_reward"
SERVICE_REMOVE_REWARD = "remove_reward"
SERVICE_REQUEST_REDEMPTION = "request_redemption"
SERVICE_APPROVE_REDEMPTION = "approve_redemption"
SERVICE_REJECT_REDEMPTION = "reject_redemption"

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
ATTR_DUE_DATE = "due_date"
ATTR_AMOUNT = "amount"
ATTR_REASON = "reason"

# Prämien-System
ATTR_REWARD_ID = "reward_id"
ATTR_REDEMPTION_ID = "redemption_id"
ATTR_COST = "cost"
ATTR_REWARD_TYPE = "reward_type"
ATTR_SWITCH_ENTITY_ID = "switch_entity_id"
ATTR_DURATION_MINUTES = "duration_minutes"

REWARD_TYPE_GENERIC = "generic"
REWARD_TYPE_INTERNET_TIME = "internet_time"

REDEMPTION_STATUS_PENDING = "pending_approval"
REDEMPTION_STATUS_APPROVED = "approved"
REDEMPTION_STATUS_REJECTED = "rejected"

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
ATTR_TRIGGER_FROM_STATE = "trigger_from_state"
ATTR_TRIGGER_ABOVE = "trigger_above"
ATTR_TRIGGER_BELOW = "trigger_below"

# Fälligkeit / Erinnerung
ATTR_DUE_IN_DAYS = "due_in_days"
ATTR_REMINDER_DAYS = "reminder_days"

# Punktabzug
ATTR_AMOUNT = "amount"
ATTR_REASON = "reason"

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

# Unique-ID der globalen Sensor-Entität, die die Anzahl ALLER offenen
# Aufgaben (unabhängig vom Benutzer) als Zustand liefert. Die
# eigentliche Aufgabenliste steht NICHT mehr als Attribut zur
# Verfügung (siehe PANEL_DATEN_DATEINAME) - dieser Sensor dient nur
# noch als Live-Signal, damit das Panel weiß, WANN es die aktuellen
# Daten neu abrufen muss.
ALL_TASKS_SENSOR_UNIQUE_ID = f"{DOMAIN}_alle_offenen_aufgaben"

# Analoge reine Zähler-Sensoren für die übrigen, potenziell großen
# Datenmengen (siehe Docstring von AufgabenScoreboardManager für den
# Hintergrund: Speicherung der eigentlichen Daten als JSON-Datei statt
# als Sensor-Attribut, um die Home-Assistant-Grenze von 16 KB pro
# Zustandsattribut nicht zu erreichen).
STANDARDAUFGABEN_SENSOR_UNIQUE_ID = f"{DOMAIN}_standardaufgaben"
PRAEMIEN_SENSOR_UNIQUE_ID = f"{DOMAIN}_praemien"
WARTENDE_AUFGABEN_SENSOR_UNIQUE_ID = f"{DOMAIN}_wartende_aufgaben"
WARTENDE_PRAEMIEN_SENSOR_UNIQUE_ID = f"{DOMAIN}_wartende_praemien"

# Kleines, eindeutiges Marker-Attribut (einzelner String, keine Liste),
# über das das Panel-JS die fünf Zähler-Sensoren dieser Integration
# unter allen "sensor."-Entitäten zuverlässig wiederfindet - unabhängig
# von Sprache/Anzeigename. Wert = jeweils einer der SENSOR_KIND_*-Werte.
ATTR_SENSOR_KIND = "aufgaben_scoreboard_sensor_kind"
SENSOR_KIND_OFFENE_AUFGABEN = "offene_aufgaben"
SENSOR_KIND_STANDARDAUFGABEN = "standardaufgaben"
SENSOR_KIND_PRAEMIEN = "praemien"
SENSOR_KIND_WARTENDE_AUFGABEN = "wartende_aufgaben"
SENSOR_KIND_WARTENDE_PRAEMIEN = "wartende_praemien"

# Datei, in der die eigentlichen (potenziell großen) Panel-Daten als
# JSON abgelegt werden - unter config/www/, damit Home Assistant sie
# automatisch und ohne jede eigene Registrierung unter /local/ ausliefert
# (derselbe, offiziell dokumentierte Mechanismus wie bei ha-rezepte).
PANEL_DATEN_ORDNER = DOMAIN
PANEL_DATEN_DATEINAME = "daten.json"

# -----------------------------------------------------------------------
# Options-Flow: Auswahl, welche Home-Assistant-Benutzer von dieser
# Integration berücksichtigt werden (eigener Punkte-Sensor + in
# Zuweisungslisten wählbar). Damit lassen sich z. B. technische
# Benutzer/Integrations-Accounts, die zwar aktiv aber keine "echten"
# Haushaltsmitglieder sind, gezielt ausblenden.
# -----------------------------------------------------------------------

OPTION_ENABLED_USERS = "enabled_users"

# Prämien-System (Punktekonto + einlösbare Prämien) ist standardmäßig
# AUS - nur wer es explizit aktiviert, sieht die zugehörigen
# Panel-Bereiche und Sensor-Attribute.
OPTION_REWARDS_ENABLED = "rewards_enabled"
