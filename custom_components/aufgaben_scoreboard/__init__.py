"""
Integration "Aufgaben-Punktesystem" für Home Assistant.

Diese Datei ist der Einstiegspunkt der Integration. Home Assistant ruft
zwei getrennte Setup-Funktionen auf:

    - async_setup(): EINMAL pro Home-Assistant-Prozess (nicht bei jedem
      Neuladen des Config-Entries) - hier wird der statische
      Frontend-Pfad registriert und die Custom Card als
      Lovelace-Ressource eingetragen. Diese Trennung UND das direkte
      Arbeiten mit dem echten hass.data["lovelace"]-Objekt (statt einer
      eigenen, separaten Store-Instanz) folgt dem offiziellen
      Community-Leitfaden "Developer Guide: Embedded Lovelace Card in a
      Home Assistant Integration" (Jan/Feb 2026) und umgeht damit
      gezielt einen bestätigten Home-Assistant-Core-Bug (#165767): Die
      Lovelace-Ressourcen-Sammlung wird lazy geladen; ein roher,
      separater Store-Zugriff kann mit dem echten Objekt kollidieren
      und bestehende Einträge überschreiben.
    - async_setup_entry(): einmal pro eingerichtetem Config-Entry (bei
      dieser Integration wegen "single_config_entry": true faktisch nur
      einmal insgesamt, kann aber bei jedem Neuladen erneut laufen).
      Hier passiert alles, was an den Lebenszyklus des Entries gebunden
      ist: Datenmanager, Sensoren, Services, Sidebar-Panel.

Aufgaben von async_setup_entry():
    1. Den zentralen Datenmanager (AufgabenScoreboardManager) erstellen
       und dessen gespeicherte Daten laden.
    2. Die Sensor-Plattform (ein Sensor pro Home-Assistant-Benutzer)
       weiterleiten (siehe sensor.py).
    3. Die Home-Assistant-Services registrieren (add_task, remove_task,
       assign_task, unassign_task, complete_task, approve_task,
       reject_task, undo_completion, reset_score, ...), damit diese in
       Automationen/Skripten UND vom Sidebar-Panel aus aufgerufen
       werden können.
    4. Das Sidebar-Panel bei Home Assistant registrieren (der statische
       Pfad dafür wurde bereits in async_setup() eingerichtet).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_call_later
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_AMOUNT,
    ATTR_ASSIGNED_TO,
    ATTR_COMPLETION_ID,
    ATTR_COST,
    ATTR_DESCRIPTION,
    ATTR_DUE_IN_DAYS,
    ATTR_DURATION_MINUTES,
    ATTR_MULTISCORING,
    ATTR_NAME,
    ATTR_REASON,
    ATTR_REDEMPTION_ID,
    ATTR_REMINDER_DAYS,
    ATTR_REWARD_ID,
    ATTR_REWARD_TYPE,
    ATTR_SCHEDULE_INTERVAL,
    ATTR_SCHEDULE_TYPE,
    ATTR_SCHEDULE_WEEKDAY,
    ATTR_SCORE,
    ATTR_SWITCH_ENTITY_ID,
    ATTR_TASK_ID,
    ATTR_TEMPLATE_ID,
    ATTR_TRIGGER_ABOVE,
    ATTR_TRIGGER_BELOW,
    ATTR_TRIGGER_ENTITY_ID,
    ATTR_TRIGGER_FROM_STATE,
    ATTR_TRIGGER_STATE,
    ATTR_USER_ID,
    CARD_JS_FILENAME,
    DOMAIN,
    FRONTEND_URL_BASE,
    INTEGRATION_VERSION,
    OPTION_REWARDS_ENABLED,
    PANEL_ICON,
    PANEL_JS_FILENAME,
    PANEL_TITLE,
    PANEL_URL_PATH,
    PLATFORMS,
    REWARD_TYPE_GENERIC,
    REWARD_TYPE_INTERNET_TIME,
    SCHEDULE_TYPE_DAYS,
    SCHEDULE_TYPE_WEEKLY,
    SERVICE_ADD_REWARD,
    SERVICE_ADD_TASK,
    SERVICE_ADD_TEMPLATE,
    SERVICE_APPROVE_REDEMPTION,
    SERVICE_APPROVE_TASK,
    SERVICE_ASSIGN_TASK,
    SERVICE_COMPLETE_TASK,
    SERVICE_CREATE_TASK_FROM_TEMPLATE,
    SERVICE_DEDUCT_POINTS,
    SERVICE_PERFORM_AWARDS,
    SERVICE_REJECT_REDEMPTION,
    SERVICE_REJECT_TASK,
    SERVICE_REMOVE_REWARD,
    SERVICE_REMOVE_TASK,
    SERVICE_REMOVE_TEMPLATE,
    SERVICE_REQUEST_REDEMPTION,
    SERVICE_RESET_SCORE,
    SERVICE_RESET_WINS,
    SERVICE_UNASSIGN_TASK,
    SERVICE_UNDO_COMPLETION,
    SERVICE_UPDATE_REWARD,
    SERVICE_UPDATE_TASK,
    SERVICE_UPDATE_TEMPLATE,
)
from .manager import AufgabenScoreboardManager

_LOGGER = logging.getLogger(__name__)

# Verzeichnis, in dem die JavaScript-Dateien (Panel + Custom Card)
# innerhalb dieser Integration liegen.
FRONTEND_DIR = Path(__file__).parent / "frontend"


# ---------------------------------------------------------------------
# Validierungs-Schemas für die einzelnen Service-Aufrufe.
# Diese sorgen dafür, dass fehlerhafte Aufrufe (z. B. fehlende Felder,
# falsche Datentypen) mit einer verständlichen Fehlermeldung abgelehnt
# werden, statt die Integration zum Absturz zu bringen.
# ---------------------------------------------------------------------

SCHEMA_ADD_TASK = vol.Schema(
    {
        vol.Required(ATTR_NAME): cv.string,
        vol.Optional(ATTR_DESCRIPTION, default=""): cv.string,
        vol.Required(ATTR_SCORE): vol.Coerce(int),
        vol.Optional(ATTR_ASSIGNED_TO, default=[]): vol.All(
            cv.ensure_list, [cv.string]
        ),
        vol.Optional(ATTR_DUE_IN_DAYS): vol.Coerce(int),
        vol.Optional(ATTR_REMINDER_DAYS): vol.Coerce(int),
    }
)

SCHEMA_UPDATE_TASK = vol.Schema(
    {
        vol.Required(ATTR_TASK_ID): cv.string,
        # Alle inhaltlichen Felder sind beim Bearbeiten optional - nur
        # tatsächlich übergebene Felder werden geändert (siehe
        # AufgabenScoreboardManager.async_update_task). Für due_in_days/
        # reminder_days entfernt ein LEERER String die jeweilige
        # Bedingung bewusst.
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_DESCRIPTION): cv.string,
        vol.Optional(ATTR_SCORE): vol.Coerce(int),
        vol.Optional(ATTR_ASSIGNED_TO): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_DUE_IN_DAYS): vol.Any(vol.Coerce(int), ""),
        vol.Optional(ATTR_REMINDER_DAYS): vol.Any(vol.Coerce(int), ""),
    }
)

SCHEMA_REMOVE_TASK = vol.Schema({vol.Required(ATTR_TASK_ID): cv.string})

SCHEMA_ASSIGN_TASK = vol.Schema(
    {
        vol.Required(ATTR_TASK_ID): cv.string,
        vol.Required(ATTR_USER_ID): cv.string,
    }
)

SCHEMA_COMPLETE_TASK = vol.Schema(
    {
        vol.Required(ATTR_TASK_ID): cv.string,
        # user_id optional: fehlt er, wird der aufrufende Benutzer
        # verwendet (praktisch beim Aufruf über das Panel).
        vol.Optional(ATTR_USER_ID): cv.string,
    }
)

SCHEMA_RESET_SCORE = vol.Schema({vol.Required(ATTR_USER_ID): cv.string})

SCHEMA_DEDUCT_POINTS = vol.Schema(
    {
        vol.Required(ATTR_USER_ID): cv.string,
        vol.Required(ATTR_AMOUNT): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional(ATTR_REASON, default=""): cv.string,
    }
)

# -----------------------------------------------------------------------
# Freigabe-Workflow
# -----------------------------------------------------------------------

SCHEMA_APPROVE_TASK = vol.Schema({vol.Required(ATTR_TASK_ID): cv.string})
SCHEMA_REJECT_TASK = vol.Schema({vol.Required(ATTR_TASK_ID): cv.string})
SCHEMA_UNDO_COMPLETION = vol.Schema({vol.Required(ATTR_COMPLETION_ID): cv.string})

# -----------------------------------------------------------------------
# Standardaufgaben (Vorlagen)
# -----------------------------------------------------------------------

SCHEMA_ADD_TEMPLATE = vol.Schema(
    {
        vol.Required(ATTR_NAME): cv.string,
        vol.Optional(ATTR_DESCRIPTION, default=""): cv.string,
        vol.Required(ATTR_SCORE): vol.Coerce(int),
        vol.Optional(ATTR_ASSIGNED_TO, default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_MULTISCORING, default=False): cv.boolean,
        # Leerer String zählt bewusst NICHT als gültige Entity-ID -
        # "kein Trigger" wird durch schlichtes Weglassen des Feldes
        # ausgedrückt, nicht durch einen leeren Wert.
        vol.Optional(ATTR_TRIGGER_ENTITY_ID): cv.entity_id,
        vol.Optional(ATTR_TRIGGER_STATE): cv.string,
        vol.Optional(ATTR_TRIGGER_FROM_STATE): cv.string,
        vol.Optional(ATTR_TRIGGER_ABOVE): vol.Coerce(float),
        vol.Optional(ATTR_TRIGGER_BELOW): vol.Coerce(float),
        # Zeitplan-Trigger (alle X Tage / jede bzw. alle X Wochen am
        # Wochentag Y) - optional, unabhängig vom Entitäts-Trigger
        # nutzbar. schedule_weekday: 0=Montag ... 6=Sonntag.
        vol.Optional(ATTR_SCHEDULE_TYPE): vol.In([SCHEDULE_TYPE_DAYS, SCHEDULE_TYPE_WEEKLY]),
        vol.Optional(ATTR_SCHEDULE_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional(ATTR_SCHEDULE_WEEKDAY): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
        vol.Optional(ATTR_DUE_IN_DAYS): vol.Coerce(int),
        vol.Optional(ATTR_REMINDER_DAYS): vol.Coerce(int),
    }
)

SCHEMA_UPDATE_TEMPLATE = vol.Schema(
    {
        vol.Required(ATTR_TEMPLATE_ID): cv.string,
        # Alle inhaltlichen Felder sind beim Bearbeiten optional - nur
        # tatsächlich übergebene Felder werden geändert (siehe
        # AufgabenScoreboardManager.async_update_template). Für die
        # Trigger-Felder gilt zusätzlich: ein LEERER String entfernt den
        # jeweiligen Trigger bewusst (siehe dortige Docstring).
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_DESCRIPTION): cv.string,
        vol.Optional(ATTR_SCORE): vol.Coerce(int),
        vol.Optional(ATTR_ASSIGNED_TO): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_MULTISCORING): cv.boolean,
        vol.Optional(ATTR_TRIGGER_ENTITY_ID): vol.Any(cv.entity_id, ""),
        vol.Optional(ATTR_TRIGGER_STATE): cv.string,
        vol.Optional(ATTR_TRIGGER_FROM_STATE): cv.string,
        vol.Optional(ATTR_TRIGGER_ABOVE): vol.Any(vol.Coerce(float), ""),
        vol.Optional(ATTR_TRIGGER_BELOW): vol.Any(vol.Coerce(float), ""),
        vol.Optional(ATTR_SCHEDULE_TYPE): vol.Any(SCHEDULE_TYPE_DAYS, SCHEDULE_TYPE_WEEKLY, ""),
        vol.Optional(ATTR_SCHEDULE_INTERVAL): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional(ATTR_SCHEDULE_WEEKDAY): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
        vol.Optional(ATTR_DUE_IN_DAYS): vol.Any(vol.Coerce(int), ""),
        vol.Optional(ATTR_REMINDER_DAYS): vol.Any(vol.Coerce(int), ""),
    }
)

SCHEMA_REMOVE_TEMPLATE = vol.Schema({vol.Required(ATTR_TEMPLATE_ID): cv.string})

SCHEMA_CREATE_TASK_FROM_TEMPLATE = vol.Schema({vol.Required(ATTR_TEMPLATE_ID): cv.string})

# -----------------------------------------------------------------------
# Siegerehrung
# -----------------------------------------------------------------------

SCHEMA_PERFORM_AWARDS = vol.Schema({})

SCHEMA_RESET_WINS = vol.Schema({vol.Required(ATTR_USER_ID): cv.string})

# -----------------------------------------------------------------------
# Prämien-System
# -----------------------------------------------------------------------

SCHEMA_ADD_REWARD = vol.Schema(
    {
        vol.Required(ATTR_NAME): cv.string,
        vol.Optional(ATTR_DESCRIPTION, default=""): cv.string,
        vol.Required(ATTR_COST): vol.Coerce(int),
        vol.Optional(ATTR_REWARD_TYPE, default=REWARD_TYPE_GENERIC): vol.In(
            [REWARD_TYPE_GENERIC, REWARD_TYPE_INTERNET_TIME]
        ),
        vol.Optional(ATTR_SWITCH_ENTITY_ID): cv.entity_id,
        vol.Optional(ATTR_DURATION_MINUTES): vol.Coerce(int),
    }
)

SCHEMA_UPDATE_REWARD = vol.Schema(
    {
        vol.Required(ATTR_REWARD_ID): cv.string,
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_DESCRIPTION): cv.string,
        vol.Optional(ATTR_COST): vol.Coerce(int),
        vol.Optional(ATTR_REWARD_TYPE): vol.In([REWARD_TYPE_GENERIC, REWARD_TYPE_INTERNET_TIME]),
        vol.Optional(ATTR_SWITCH_ENTITY_ID): vol.Any(cv.entity_id, ""),
        vol.Optional(ATTR_DURATION_MINUTES): vol.Coerce(int),
    }
)

SCHEMA_REMOVE_REWARD = vol.Schema({vol.Required(ATTR_REWARD_ID): cv.string})

SCHEMA_REQUEST_REDEMPTION = vol.Schema(
    {
        vol.Required(ATTR_REWARD_ID): cv.string,
        vol.Optional(ATTR_USER_ID): cv.string,
    }
)

SCHEMA_APPROVE_REDEMPTION = vol.Schema({vol.Required(ATTR_REDEMPTION_ID): cv.string})

SCHEMA_REJECT_REDEMPTION = vol.Schema({vol.Required(ATTR_REDEMPTION_ID): cv.string})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """
    Domain-weites Setup - läuft EINMAL pro Home-Assistant-Prozess, noch
    bevor async_setup_entry() für den (einzigen) Config-Entry aufgerufen
    wird, und wird NICHT erneut ausgeführt, wenn der Entry später neu
    geladen wird. Registriert deshalb hier (statt in async_setup_entry)
    alles, was wirklich nur einmal pro laufendem Home Assistant
    passieren muss: den statischen Frontend-Pfad (liefert sowohl die
    Panel- als auch die Karten-JS-Datei aus) sowie die Custom Card als
    Lovelace-Ressource. Siehe Datei-Docstring für den Hintergrund.
    """

    async def _setup_frontend(_event=None) -> None:
        await _async_register_static_path(hass)
        await _async_register_card_resource(hass)

    if hass.state is CoreState.running:
        await _setup_frontend()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _setup_frontend)

    return True


async def _async_register_static_path(hass: HomeAssistant) -> None:
    """
    Registriert den statischen Pfad /aufgaben_scoreboard_frontend/, der
    das komplette frontend/-Verzeichnis (Panel- UND Karten-JS)
    ausliefert - ein einziger Aufruf deckt beide Dateien ab.
    """
    try:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    FRONTEND_URL_BASE,
                    str(FRONTEND_DIR),
                    cache_headers=False,
                )
            ]
        )
        _LOGGER.debug("Statischer Frontend-Pfad registriert: %s", FRONTEND_URL_BASE)
    except RuntimeError:
        # Kann bei einem echten Home-Assistant-Neustart mit bereits
        # vorhandenen alten Zustandsresten passieren - da diese
        # Registrierung dank async_setup() jetzt ohnehin nur einmal pro
        # Prozess läuft, ist das nur noch eine zusätzliche Absicherung,
        # kein regulärer Fall mehr.
        _LOGGER.debug("Statischer Frontend-Pfad '%s' war bereits registriert.", FRONTEND_URL_BASE)


async def _async_register_card_resource(hass: HomeAssistant) -> None:
    """
    Trägt die Custom Card als Lovelace-Ressource ein - über das ECHTE,
    laufende Home-Assistant-Lovelace-Objekt (hass.data["lovelace"]),
    NICHT über eine eigene, separate Store-Instanz. Nur im
    Storage-Modus möglich (Standardfall); im YAML-Modus muss die
    Ressource manuell eingetragen werden (siehe README).
    """
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        _LOGGER.warning(
            "Lovelace-Komponente war beim Registrieren der Custom Card noch nicht bereit - "
            "sie steht ggf. erst nach einem erneuten Neustart zur Verfügung."
        )
        return

    # WICHTIG: Bestätigter Breaking Change in Home Assistant seit
    # 2026.2 (Übergangsfrist bis 2026.8, inzwischen abgelaufen): Das
    # Attribut heißt nicht mehr "mode", sondern "resource_mode". Ohne
    # diesen Fallback würde getattr(lovelace, "mode", None) auf neueren
    # HA-Versionen immer None liefern - die Integration würde dann
    # fälschlich IMMER "YAML-Modus" annehmen und die automatische
    # Registrierung überspringen, selbst im ganz normalen Storage-Modus.
    lovelace_modus = getattr(lovelace, "resource_mode", None) or getattr(lovelace, "mode", None)
    if lovelace_modus != "storage":
        _LOGGER.info(
            "Lovelace läuft im YAML-Modus - die Custom Card muss dort manuell als Ressource "
            "eingetragen werden (URL: %s/%s). Siehe README.",
            FRONTEND_URL_BASE,
            CARD_JS_FILENAME,
        )
        return

    await _async_warte_auf_lovelace_ressourcen(hass, lovelace)


async def _async_warte_auf_lovelace_ressourcen(hass: HomeAssistant, lovelace: Any) -> None:
    """
    Wartet - mit Wiederholung alle 5 Sekunden - bis Home Assistants
    eigene Lovelace-Ressourcen-Sammlung fertig von der Festplatte
    geladen ist (lovelace.resources.loaded), bevor darauf zugegriffen
    wird. Genau das umgeht den bekannten Lazy-Load-Bug (siehe
    Datei-Docstring): Zugriffe VOR dem vollständigen Laden würden eine
    leere Sammlung sehen und könnten bestehende Einträge überschreiben.
    """

    async def _pruefen(_now: Any = None) -> None:
        if lovelace.resources.loaded:
            await _async_karte_als_ressource_eintragen(lovelace)
        else:
            _LOGGER.debug("Lovelace-Ressourcen noch nicht geladen - erneuter Versuch in 5s.")
            async_call_later(hass, 5, _pruefen)

    await _pruefen()


async def _async_karte_als_ressource_eintragen(lovelace: Any) -> None:
    """
    Legt den Lovelace-Ressourcen-Eintrag für die Custom Card an, bzw.
    aktualisiert dessen Versions-Parameter, falls sich die
    Integrations-Version seit dem letzten Eintrag geändert hat
    (Cache-Busting: Browser laden nach einem Update zuverlässig die
    neue Datei statt einer alten, gecachten Version).
    """
    karten_url_ohne_version = f"{FRONTEND_URL_BASE}/{CARD_JS_FILENAME}"
    versionierte_url = f"{karten_url_ohne_version}?v={INTEGRATION_VERSION}"

    vorhandene_eintraege = [
        eintrag
        for eintrag in lovelace.resources.async_items()
        if eintrag["url"].split("?")[0] == karten_url_ohne_version
    ]

    if not vorhandene_eintraege:
        await lovelace.resources.async_create_item({"res_type": "module", "url": versionierte_url})
        _LOGGER.info(
            "Aufgaben-Scoreboard: Custom Card als Lovelace-Ressource eingetragen (%s).", versionierte_url
        )
        return

    eintrag = vorhandene_eintraege[0]
    aktuell_eingetragene_version = eintrag["url"].split("?v=")[-1] if "?v=" in eintrag["url"] else None
    if aktuell_eingetragene_version != INTEGRATION_VERSION:
        await lovelace.resources.async_update_item(eintrag["id"], {"res_type": "module", "url": versionierte_url})
        _LOGGER.info("Aufgaben-Scoreboard: Custom Card auf Version %s aktualisiert.", INTEGRATION_VERSION)
    else:
        _LOGGER.debug("Aufgaben-Scoreboard: Custom Card war bereits in aktueller Version eingetragen.")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    Wird von Home Assistant beim Laden der Integration aufgerufen
    (einmal pro eingerichtetem Config-Entry - diese Integration erlaubt
    laut manifest.json ("single_config_entry": true) aber nur genau
    einen Eintrag).
    """
    hass.data.setdefault(DOMAIN, {})

    # ------------------------------------------------------------------
    # 1. Datenmanager erstellen und gespeicherte Daten laden
    # ------------------------------------------------------------------
    manager = AufgabenScoreboardManager(hass)
    try:
        await manager.async_load()
    except OSError as fehler:
        # Falls die Storage-Datei aus irgendeinem Grund nicht lesbar ist,
        # brechen wir das Setup ab - Home Assistant versucht es dann
        # automatisch später erneut.
        raise ConfigEntryNotReady(f"Aufgaben-Daten konnten nicht geladen werden: {fehler}") from fehler

    hass.data[DOMAIN][entry.entry_id] = manager

    # Entitäts-Trigger für Standardaufgaben (falls konfiguriert) jetzt
    # abonnieren, damit automatische Aufgaben-Anlage direkt nach dem
    # Start der Integration funktioniert.
    manager.sync_trigger_listeners()

    # Zeitplan-Trigger für Standardaufgaben (alle X Tage / jede bzw.
    # alle X Wochen am Wochentag Y, falls konfiguriert) jetzt ebenfalls
    # aktivieren - inkl. einmaliger Nachhol-Prüfung für den aktuellen Tag.
    manager.async_setup_schedule()

    # Internet-Zeit-Prämien: für alle bereits freigegebenen, noch aktiven
    # Einlösungen die Restlaufzeit prüfen und ggf. sofort nachholend
    # abschalten oder den Abschalt-Timer neu setzen (siehe Docstring von
    # async_setup_reward_timers() - relevant nach einem HA-Neustart,
    # während dessen der ursprüngliche Timer verloren ging).
    manager.async_setup_reward_timers()

    # ------------------------------------------------------------------
    # 2. Sensor-Plattform laden (ein Sensor pro Benutzer + Übersicht)
    # ------------------------------------------------------------------
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ------------------------------------------------------------------
    # 3. Services registrieren
    # ------------------------------------------------------------------
    _async_register_services(hass, entry, manager)

    # ------------------------------------------------------------------
    # 4. Frontend (Sidebar-Panel) registrieren
    #
    # WICHTIG: async_register_static_paths() und
    # async_register_built_in_panel() dürfen erst aufgerufen werden,
    # wenn das Frontend-Backend von Home Assistant vollständig bereit
    # ist. Bei einem echten Neustart (nicht bei einem reinen Reload der
    # Integration) ist async_setup_entry() aber unter Umständen schon
    # VOR diesem Zeitpunkt fertig - ruft man die Registrierung dann
    # direkt auf, kann sie ins Leere laufen und Karte/Panel bleiben
    # nicht verfügbar. Ist hass.state bereits "running", ist alles
    # bereit und wir registrieren sofort; andernfalls warten wir auf
    # das EVENT_HOMEASSISTANT_STARTED-Event.
    # ------------------------------------------------------------------
    if hass.state is CoreState.running:
        await _async_setup_frontend(hass)
    else:
        # WICHTIG: hass.bus.async_listen_once() liefert einen Listener,
        # der sich nach dem Feuern SELBST aus dem Event-Bus entfernt.
        # Würde man das dabei zurückgegebene Unsub trotzdem noch unverändert
        # an entry.async_on_unload() weiterreichen, versucht Home Assistant
        # beim nächsten Entladen/Neuladen der Integration (falls das NACH
        # dem HA-Start passiert), denselben - inzwischen bereits selbst
        # entfernten - Listener ein zweites Mal zu entfernen. Das führt zu
        # "Unable to remove unknown job listener" (ValueError) im Log.
        # Daher: merken, ob der Listener schon gefeuert hat, und das
        # Unsub beim Entladen nur dann noch aufrufen, wenn nicht.
        listener_hat_gefeuert = False

        async def _async_setup_frontend_on_start(_event) -> None:
            nonlocal listener_hat_gefeuert
            listener_hat_gefeuert = True
            await _async_setup_frontend(hass)

        unsub_listener = hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_setup_frontend_on_start)

        @callback
        def _async_listener_sicher_abmelden() -> None:
            if not listener_hat_gefeuert:
                unsub_listener()

        entry.async_on_unload(_async_listener_sicher_abmelden)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Wird beim Entfernen/Neuladen der Integration aufgerufen."""
    entladen_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if entladen_ok:
        manager: AufgabenScoreboardManager = hass.data[DOMAIN].pop(entry.entry_id)
        # Entitäts-Trigger-Listener der Standardaufgaben sauber abmelden.
        manager.async_unload()

        # Services nur entfernen, wenn keine weiteren Einträge mehr aktiv
        # sind (bei single_config_entry ist das faktisch immer der Fall).
        if not hass.data[DOMAIN]:
            for service in (
                SERVICE_ADD_TASK,
                SERVICE_UPDATE_TASK,
                SERVICE_REMOVE_TASK,
                SERVICE_ASSIGN_TASK,
                SERVICE_UNASSIGN_TASK,
                SERVICE_COMPLETE_TASK,
                SERVICE_APPROVE_TASK,
                SERVICE_REJECT_TASK,
                SERVICE_UNDO_COMPLETION,
                SERVICE_RESET_SCORE,
                SERVICE_DEDUCT_POINTS,
                SERVICE_RESET_WINS,
                SERVICE_ADD_REWARD,
                SERVICE_UPDATE_REWARD,
                SERVICE_REMOVE_REWARD,
                SERVICE_REQUEST_REDEMPTION,
                SERVICE_APPROVE_REDEMPTION,
                SERVICE_REJECT_REDEMPTION,
                SERVICE_ADD_TEMPLATE,
                SERVICE_UPDATE_TEMPLATE,
                SERVICE_REMOVE_TEMPLATE,
                SERVICE_CREATE_TASK_FROM_TEMPLATE,
            ):
                hass.services.async_remove(DOMAIN, service)

            async_remove_panel(hass, PANEL_URL_PATH)

    return entladen_ok


# -----------------------------------------------------------------------
# Hilfsfunktionen
# -----------------------------------------------------------------------


async def _ist_admin(hass: HomeAssistant, call: ServiceCall) -> bool:
    """
    Prüft, ob der Benutzer, der den Service-Aufruf ausgelöst hat, ein
    Administrator ist. Wird für sicherheitsrelevante Aktionen (Aufgaben
    anlegen/löschen/zuweisen, Punkte zurücksetzen) verwendet, damit
    normale Benutzer nur ihre eigenen Aufgaben erledigen können.

    Wird der Service intern (z. B. aus einer Automation ohne
    Benutzerkontext) aufgerufen, gibt es keine user_id - in diesem Fall
    wird der Aufruf ebenfalls erlaubt, da Automationen/Skripte ohnehin
    nur von Administratoren bearbeitet werden können.

    Hinweis: hass.auth.async_get_user() ist eine Coroutine und muss
    daher await'et werden - wird das vergessen, liefert die Funktion
    ein Coroutine-Objekt statt eines User-Objekts zurück, was zu einem
    "'coroutine' object has no attribute 'is_admin'"-Fehler führt.
    """
    if call.context.user_id is None:
        return True
    benutzer = await hass.auth.async_get_user(call.context.user_id)
    return bool(benutzer and benutzer.is_admin)


def _async_register_services(hass: HomeAssistant, entry: ConfigEntry, manager: AufgabenScoreboardManager) -> None:
    """Registriert alle von dieser Integration bereitgestellten Services."""

    async def handle_add_task(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Aufgabe anzulegen - abgelehnt.")
            return
        await manager.async_add_task(
            name=call.data[ATTR_NAME],
            description=call.data.get(ATTR_DESCRIPTION, ""),
            score=call.data[ATTR_SCORE],
            assigned_to=call.data.get(ATTR_ASSIGNED_TO, []),
            due_in_days=call.data.get(ATTR_DUE_IN_DAYS),
            reminder_days=call.data.get(ATTR_REMINDER_DAYS),
        )

    async def handle_update_task(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Aufgabe zu bearbeiten - abgelehnt.")
            return
        await manager.async_update_task(
            task_id=call.data[ATTR_TASK_ID],
            name=call.data.get(ATTR_NAME),
            description=call.data.get(ATTR_DESCRIPTION),
            score=call.data.get(ATTR_SCORE),
            assigned_to=call.data.get(ATTR_ASSIGNED_TO),
            due_in_days=call.data.get(ATTR_DUE_IN_DAYS),
            reminder_days=call.data.get(ATTR_REMINDER_DAYS),
        )

    async def handle_remove_task(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Aufgabe zu löschen - abgelehnt.")
            return
        await manager.async_remove_task(call.data[ATTR_TASK_ID])

    async def handle_assign_task(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Aufgabe zuzuweisen - abgelehnt.")
            return
        await manager.async_assign_task(call.data[ATTR_TASK_ID], call.data[ATTR_USER_ID])

    async def handle_unassign_task(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Zuweisung zu entfernen - abgelehnt.")
            return
        await manager.async_unassign_task(call.data[ATTR_TASK_ID], call.data[ATTR_USER_ID])

    async def handle_complete_task(call: ServiceCall) -> None:
        # Wird kein user_id mitgegeben, wird der aufrufende Benutzer
        # verwendet - das ist der Normalfall bei Nutzung über das
        # Sidebar-Panel.
        user_id = call.data.get(ATTR_USER_ID) or call.context.user_id
        if not user_id:
            _LOGGER.error(
                "complete_task: Es konnte kein Benutzer ermittelt werden "
                "(weder user_id angegeben noch Aufrufkontext vorhanden)."
            )
            return

        # Ein normaler Benutzer darf nur SEINE EIGENEN Aufgaben erledigen.
        # Administratoren dürfen dies stellvertretend für jeden Benutzer tun.
        if call.context.user_id and call.context.user_id != user_id and not await _ist_admin(hass, call):
            _LOGGER.warning(
                "Benutzer hat versucht, eine Aufgabe für einen anderen Benutzer "
                "zu erledigen, ohne Administrator zu sein - abgelehnt."
            )
            return

        await manager.async_complete_task(call.data[ATTR_TASK_ID], user_id)

    async def handle_approve_task(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Aufgabe freizugeben - abgelehnt.")
            return
        await manager.async_approve_task(call.data[ATTR_TASK_ID])

    async def handle_reject_task(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Aufgabe abzulehnen - abgelehnt.")
            return
        await manager.async_reject_task(call.data[ATTR_TASK_ID])

    async def handle_undo_completion(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Erledigung zurückzunehmen - abgelehnt.")
            return
        await manager.async_undo_completion(call.data[ATTR_COMPLETION_ID])

    async def handle_reset_score(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, einen Punktestand zurückzusetzen - abgelehnt.")
            return
        await manager.async_reset_score(call.data[ATTR_USER_ID])

    async def handle_perform_awards(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Siegerehrung durchzuführen - abgelehnt.")
            return
        praemien_aktiviert = entry.options.get(OPTION_REWARDS_ENABLED, False)
        await manager.async_perform_awards(praemien_aktiviert)

    async def handle_reset_wins(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, einen Sieg-Zähler zurückzusetzen - abgelehnt.")
            return
        await manager.async_reset_wins(call.data[ATTR_USER_ID])

    async def handle_add_reward(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Prämie anzulegen - abgelehnt.")
            return
        await manager.async_add_reward(
            name=call.data[ATTR_NAME],
            description=call.data.get(ATTR_DESCRIPTION, ""),
            cost=call.data[ATTR_COST],
            reward_type=call.data.get(ATTR_REWARD_TYPE, REWARD_TYPE_GENERIC),
            switch_entity_id=call.data.get(ATTR_SWITCH_ENTITY_ID),
            duration_minutes=call.data.get(ATTR_DURATION_MINUTES),
        )

    async def handle_update_reward(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Prämie zu bearbeiten - abgelehnt.")
            return
        await manager.async_update_reward(
            reward_id=call.data[ATTR_REWARD_ID],
            name=call.data.get(ATTR_NAME),
            description=call.data.get(ATTR_DESCRIPTION),
            cost=call.data.get(ATTR_COST),
            reward_type=call.data.get(ATTR_REWARD_TYPE),
            switch_entity_id=call.data.get(ATTR_SWITCH_ENTITY_ID),
            duration_minutes=call.data.get(ATTR_DURATION_MINUTES),
        )

    async def handle_remove_reward(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Prämie zu löschen - abgelehnt.")
            return
        await manager.async_remove_reward(call.data[ATTR_REWARD_ID])

    async def handle_request_redemption(call: ServiceCall) -> None:
        # Wird kein user_id mitgegeben, wird der aufrufende Benutzer
        # verwendet - Normalfall bei Nutzung über das Sidebar-Panel.
        user_id = call.data.get(ATTR_USER_ID) or call.context.user_id
        if not user_id:
            _LOGGER.error(
                "request_redemption: Es konnte kein Benutzer ermittelt werden "
                "(weder user_id angegeben noch Aufrufkontext vorhanden)."
            )
            return
        # Ein normaler Benutzer darf nur FÜR SICH SELBST eine Prämie
        # anfragen. Administratoren dürfen dies stellvertretend tun.
        if call.context.user_id and call.context.user_id != user_id and not await _ist_admin(hass, call):
            _LOGGER.warning(
                "Benutzer hat versucht, eine Prämie für einen anderen Benutzer "
                "anzufragen, ohne Administrator zu sein - abgelehnt."
            )
            return
        await manager.async_request_redemption(call.data[ATTR_REWARD_ID], user_id)

    async def handle_approve_redemption(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Einlösung freizugeben - abgelehnt.")
            return
        await manager.async_approve_redemption(call.data[ATTR_REDEMPTION_ID])

    async def handle_reject_redemption(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Einlösung abzulehnen - abgelehnt.")
            return
        await manager.async_reject_redemption(call.data[ATTR_REDEMPTION_ID])

    async def handle_add_template(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Standardaufgabe anzulegen - abgelehnt.")
            return
        await manager.async_add_template(
            name=call.data[ATTR_NAME],
            description=call.data.get(ATTR_DESCRIPTION, ""),
            score=call.data[ATTR_SCORE],
            assigned_to=call.data.get(ATTR_ASSIGNED_TO, []),
            multiscoring=call.data.get(ATTR_MULTISCORING, False),
            trigger_entity_id=call.data.get(ATTR_TRIGGER_ENTITY_ID),
            trigger_state=call.data.get(ATTR_TRIGGER_STATE),
            trigger_from_state=call.data.get(ATTR_TRIGGER_FROM_STATE),
            trigger_above=call.data.get(ATTR_TRIGGER_ABOVE),
            trigger_below=call.data.get(ATTR_TRIGGER_BELOW),
            schedule_type=call.data.get(ATTR_SCHEDULE_TYPE),
            schedule_interval=call.data.get(ATTR_SCHEDULE_INTERVAL),
            schedule_weekday=call.data.get(ATTR_SCHEDULE_WEEKDAY),
            due_in_days=call.data.get(ATTR_DUE_IN_DAYS),
            reminder_days=call.data.get(ATTR_REMINDER_DAYS),
        )

    async def handle_update_template(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Standardaufgabe zu bearbeiten - abgelehnt.")
            return
        await manager.async_update_template(
            template_id=call.data[ATTR_TEMPLATE_ID],
            name=call.data.get(ATTR_NAME),
            description=call.data.get(ATTR_DESCRIPTION),
            score=call.data.get(ATTR_SCORE),
            assigned_to=call.data.get(ATTR_ASSIGNED_TO),
            multiscoring=call.data.get(ATTR_MULTISCORING),
            trigger_entity_id=call.data.get(ATTR_TRIGGER_ENTITY_ID),
            trigger_state=call.data.get(ATTR_TRIGGER_STATE),
            trigger_from_state=call.data.get(ATTR_TRIGGER_FROM_STATE),
            trigger_above=call.data.get(ATTR_TRIGGER_ABOVE),
            trigger_below=call.data.get(ATTR_TRIGGER_BELOW),
            schedule_type=call.data.get(ATTR_SCHEDULE_TYPE),
            schedule_interval=call.data.get(ATTR_SCHEDULE_INTERVAL),
            schedule_weekday=call.data.get(ATTR_SCHEDULE_WEEKDAY),
            due_in_days=call.data.get(ATTR_DUE_IN_DAYS),
            reminder_days=call.data.get(ATTR_REMINDER_DAYS),
        )

    async def handle_remove_template(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Standardaufgabe zu löschen - abgelehnt.")
            return
        await manager.async_remove_template(call.data[ATTR_TEMPLATE_ID])

    async def handle_deduct_points(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, Punkte abzuziehen - abgelehnt.")
            return
        await manager.async_deduct_points(
            user_id=call.data[ATTR_USER_ID],
            amount=call.data[ATTR_AMOUNT],
            reason=call.data.get(ATTR_REASON, ""),
        )

    async def handle_create_task_from_template(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning(
                "Nicht-Administrator hat versucht, eine Aufgabe aus einer Standardaufgabe anzulegen - abgelehnt."
            )
            return
        await manager.async_create_task_from_template(call.data[ATTR_TEMPLATE_ID])

    hass.services.async_register(DOMAIN, SERVICE_ADD_TASK, handle_add_task, schema=SCHEMA_ADD_TASK)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_TASK, handle_update_task, schema=SCHEMA_UPDATE_TASK)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_TASK, handle_remove_task, schema=SCHEMA_REMOVE_TASK)
    hass.services.async_register(DOMAIN, SERVICE_ASSIGN_TASK, handle_assign_task, schema=SCHEMA_ASSIGN_TASK)
    hass.services.async_register(DOMAIN, SERVICE_UNASSIGN_TASK, handle_unassign_task, schema=SCHEMA_ASSIGN_TASK)
    hass.services.async_register(DOMAIN, SERVICE_COMPLETE_TASK, handle_complete_task, schema=SCHEMA_COMPLETE_TASK)
    hass.services.async_register(DOMAIN, SERVICE_RESET_SCORE, handle_reset_score, schema=SCHEMA_RESET_SCORE)
    hass.services.async_register(DOMAIN, SERVICE_DEDUCT_POINTS, handle_deduct_points, schema=SCHEMA_DEDUCT_POINTS)
    hass.services.async_register(
        DOMAIN, SERVICE_PERFORM_AWARDS, handle_perform_awards, schema=SCHEMA_PERFORM_AWARDS
    )
    hass.services.async_register(DOMAIN, SERVICE_RESET_WINS, handle_reset_wins, schema=SCHEMA_RESET_WINS)
    hass.services.async_register(DOMAIN, SERVICE_ADD_REWARD, handle_add_reward, schema=SCHEMA_ADD_REWARD)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_REWARD, handle_update_reward, schema=SCHEMA_UPDATE_REWARD)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_REWARD, handle_remove_reward, schema=SCHEMA_REMOVE_REWARD)
    hass.services.async_register(
        DOMAIN, SERVICE_REQUEST_REDEMPTION, handle_request_redemption, schema=SCHEMA_REQUEST_REDEMPTION
    )
    hass.services.async_register(
        DOMAIN, SERVICE_APPROVE_REDEMPTION, handle_approve_redemption, schema=SCHEMA_APPROVE_REDEMPTION
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REJECT_REDEMPTION, handle_reject_redemption, schema=SCHEMA_REJECT_REDEMPTION
    )
    hass.services.async_register(DOMAIN, SERVICE_APPROVE_TASK, handle_approve_task, schema=SCHEMA_APPROVE_TASK)
    hass.services.async_register(DOMAIN, SERVICE_REJECT_TASK, handle_reject_task, schema=SCHEMA_REJECT_TASK)
    hass.services.async_register(
        DOMAIN, SERVICE_UNDO_COMPLETION, handle_undo_completion, schema=SCHEMA_UNDO_COMPLETION
    )
    hass.services.async_register(DOMAIN, SERVICE_ADD_TEMPLATE, handle_add_template, schema=SCHEMA_ADD_TEMPLATE)
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_TEMPLATE, handle_update_template, schema=SCHEMA_UPDATE_TEMPLATE
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_TEMPLATE, handle_remove_template, schema=SCHEMA_REMOVE_TEMPLATE
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_TASK_FROM_TEMPLATE,
        handle_create_task_from_template,
        schema=SCHEMA_CREATE_TASK_FROM_TEMPLATE,
    )


async def _async_setup_frontend(hass: HomeAssistant) -> None:
    """
    Registriert das Sidebar-Panel bei Home Assistant.

    Der statische HTTP-Pfad, der die JS-Datei tatsächlich ausliefert,
    wird NICHT hier, sondern bereits einmalig in async_setup()
    registriert (deckt Panel- und Karten-JS gemeinsam ab). Diese
    Funktion kümmert sich nur noch um die Panel-Registrierung selbst,
    die - anders als der statische Pfad - an den Lebenszyklus dieses
    Config-Entries gebunden ist (siehe async_remove_panel() in
    async_unload_entry).
    """
    panel_pfad = FRONTEND_DIR / PANEL_JS_FILENAME

    if not panel_pfad.exists():
        _LOGGER.error(
            "Frontend-Datei des Sidebar-Panels fehlt (%s). Das Panel steht nicht zur Verfügung.",
            panel_pfad,
        )
        return

    # Sidebar-Panel registrieren. component_name "custom" sorgt dafür,
    # dass Home Assistant das angegebene JavaScript-Modul als eigenes
    # Custom-Element für die gesamte Panel-Seite lädt.
    #
    # WICHTIG: "module_url" (nicht "js_url") verwenden. "js_url" liefert
    # das Skript nur an Clients aus, die noch den alten ES5-Build des
    # Frontends nutzen, und ist der veraltete Weg. "module_url" ist die
    # aktuelle, zukunftssichere Variante, mit der das Panel als
    # ES-Modul geladen wird.
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": "aufgaben-scoreboard-panel",
                "embed_iframe": False,
                "trust_external": False,
                "module_url": f"{FRONTEND_URL_BASE}/{PANEL_JS_FILENAME}",
            }
        },
        require_admin=False,
    )
    _LOGGER.info("Aufgaben-Scoreboard: Sidebar-Panel unter '/%s' registriert.", PANEL_URL_PATH)
