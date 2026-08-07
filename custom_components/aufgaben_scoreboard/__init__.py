"""
Integration "Aufgaben-Punktesystem" für Home Assistant.

Diese Datei ist der Einstiegspunkt der Integration. Sie wird von Home
Assistant automatisch geladen, sobald die Integration über die UI
("Einstellungen -> Geräte & Dienste -> Integration hinzufügen")
eingerichtet wurde (siehe config_flow.py).

Aufgaben dieser Datei:
    1. Den zentralen Datenmanager (AufgabenScoreboardManager) erstellen
       und dessen gespeicherte Daten laden.
    2. Die Sensor-Plattform (ein Sensor pro Home-Assistant-Benutzer)
       weiterleiten (siehe sensor.py).
    3. Die Home-Assistant-Services registrieren (add_task, remove_task,
       assign_task, unassign_task, complete_task, reset_score), damit
       diese in Automationen/Skripten UND von der Custom Card / dem
       Sidebar-Panel aus aufgerufen werden können.
    4. Die statischen Frontend-Dateien (Custom Card + Sidebar-Panel als
       JavaScript-Module) unter einer festen URL bereitstellen und das
       Sidebar-Panel bei Home Assistant registrieren.
"""

from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
    add_extra_js_url,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv

from .const import (
    ATTR_ASSIGNED_TO,
    ATTR_DESCRIPTION,
    ATTR_MULTISCORING,
    ATTR_NAME,
    ATTR_SCORE,
    ATTR_TASK_ID,
    ATTR_TEMPLATE_ID,
    ATTR_TRIGGER_ENTITY_ID,
    ATTR_TRIGGER_STATE,
    ATTR_USER_ID,
    CARD_JS_FILENAME,
    DOMAIN,
    FRONTEND_URL_BASE,
    PANEL_ICON,
    PANEL_JS_FILENAME,
    PANEL_TITLE,
    PANEL_URL_PATH,
    PLATFORMS,
    SERVICE_ADD_TASK,
    SERVICE_ADD_TEMPLATE,
    SERVICE_ASSIGN_TASK,
    SERVICE_COMPLETE_TASK,
    SERVICE_CREATE_TASK_FROM_TEMPLATE,
    SERVICE_REMOVE_TASK,
    SERVICE_REMOVE_TEMPLATE,
    SERVICE_RESET_SCORE,
    SERVICE_UNASSIGN_TASK,
    SERVICE_UPDATE_TASK,
    SERVICE_UPDATE_TEMPLATE,
)
from .manager import AufgabenScoreboardManager

_LOGGER = logging.getLogger(__name__)

# Verzeichnis, in dem die JavaScript-Dateien für Panel und Custom Card
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
    }
)

SCHEMA_UPDATE_TASK = vol.Schema(
    {
        vol.Required(ATTR_TASK_ID): cv.string,
        # Alle inhaltlichen Felder sind beim Bearbeiten optional - nur
        # tatsächlich übergebene Felder werden geändert (siehe
        # AufgabenScoreboardManager.async_update_task).
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_DESCRIPTION): cv.string,
        vol.Optional(ATTR_SCORE): vol.Coerce(int),
        vol.Optional(ATTR_ASSIGNED_TO): vol.All(cv.ensure_list, [cv.string]),
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
        # verwendet (praktisch für die Custom Card).
        vol.Optional(ATTR_USER_ID): cv.string,
    }
)

SCHEMA_RESET_SCORE = vol.Schema({vol.Required(ATTR_USER_ID): cv.string})

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
    }
)

SCHEMA_UPDATE_TEMPLATE = vol.Schema(
    {
        vol.Required(ATTR_TEMPLATE_ID): cv.string,
        # Alle inhaltlichen Felder sind beim Bearbeiten optional - nur
        # tatsächlich übergebene Felder werden geändert (siehe
        # AufgabenScoreboardManager.async_update_template). Für die
        # beiden Trigger-Felder gilt zusätzlich: ein LEERER String
        # entfernt den Trigger bewusst (siehe dortige Docstring).
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_DESCRIPTION): cv.string,
        vol.Optional(ATTR_SCORE): vol.Coerce(int),
        vol.Optional(ATTR_ASSIGNED_TO): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_MULTISCORING): cv.boolean,
        vol.Optional(ATTR_TRIGGER_ENTITY_ID): vol.Any(cv.entity_id, ""),
        vol.Optional(ATTR_TRIGGER_STATE): cv.string,
    }
)

SCHEMA_REMOVE_TEMPLATE = vol.Schema({vol.Required(ATTR_TEMPLATE_ID): cv.string})

SCHEMA_CREATE_TASK_FROM_TEMPLATE = vol.Schema({vol.Required(ATTR_TEMPLATE_ID): cv.string})


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

    # ------------------------------------------------------------------
    # 2. Sensor-Plattform laden (ein Sensor pro Benutzer + Übersicht)
    # ------------------------------------------------------------------
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ------------------------------------------------------------------
    # 3. Services registrieren
    # ------------------------------------------------------------------
    _async_register_services(hass, manager)

    # ------------------------------------------------------------------
    # 4. Frontend (Custom Card + Sidebar-Panel) registrieren
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
                SERVICE_RESET_SCORE,
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


def _async_register_services(hass: HomeAssistant, manager: AufgabenScoreboardManager) -> None:
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
        # verwendet - das ist der Normalfall bei Nutzung über die
        # Custom Card / das Sidebar-Panel.
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

    async def handle_reset_score(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, einen Punktestand zurückzusetzen - abgelehnt.")
            return
        await manager.async_reset_score(call.data[ATTR_USER_ID])

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
        )

    async def handle_remove_template(call: ServiceCall) -> None:
        if not await _ist_admin(hass, call):
            _LOGGER.warning("Nicht-Administrator hat versucht, eine Standardaufgabe zu löschen - abgelehnt.")
            return
        await manager.async_remove_template(call.data[ATTR_TEMPLATE_ID])

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
    Stellt die JavaScript-Dateien (Custom Card + Panel) über einen
    statischen HTTP-Pfad bereit und registriert:
      - die Custom Card global (add_extra_js_url), damit sie in JEDER
        Dashboard-Ansicht per "type: custom:aufgaben-scoreboard-card"
        verwendet werden kann, ohne dass der Benutzer manuell eine
        Lovelace-Ressource hinzufügen muss.
      - ein eigenes Panel in der Seitenleiste, das die volle
        Aufgabenübersicht (inkl. Admin-Funktionen) als eigene Seite
        zeigt.
    """
    card_pfad = FRONTEND_DIR / CARD_JS_FILENAME
    panel_pfad = FRONTEND_DIR / PANEL_JS_FILENAME

    if not card_pfad.exists() or not panel_pfad.exists():
        _LOGGER.error(
            "Frontend-Dateien der Integration fehlen (%s). "
            "Custom Card und Sidebar-Panel stehen nicht zur Verfügung.",
            FRONTEND_DIR,
        )
        return

    # Statischen Pfad registrieren: alles unter /aufgaben_scoreboard_frontend/
    # wird aus dem lokalen "frontend"-Ordner der Integration ausgeliefert.
    #
    # WICHTIG: Wird die Integration neu geladen, OHNE dass Home Assistant
    # komplett neu gestartet wurde, kann aiohttp beim erneuten
    # Registrieren desselben Pfads mit einem RuntimeError ("Added route
    # will never be executed, method GET is already registered")
    # abbrechen - es gibt für den statischen Pfad (anders als beim Panel,
    # siehe async_remove_panel() in async_unload_entry) kein Gegenstück
    # zum Abmelden. Derselbe Fehler trat bereits konkret bei
    # ha-parcel-tracking (behoben in v1.0.4) und ha-step-challenge auf;
    # der Fix dort - gezielt NUR RuntimeError abfangen - wird hier 1:1
    # übernommen, damit dieser eine, bekannte Fall den Rest der
    # Frontend-Registrierung (Custom Card, Panel) nicht blockiert.
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
        _LOGGER.debug(
            "Statischer Frontend-Pfad '%s' war bereits registriert (normal bei "
            "einem Neuladen der Integration ohne Home-Assistant-Neustart).",
            FRONTEND_URL_BASE,
        )

    # Custom Card global für alle Dashboards verfügbar machen.
    card_url = f"{FRONTEND_URL_BASE}/{CARD_JS_FILENAME}"
    add_extra_js_url(hass, card_url)
    _LOGGER.info(
        "Aufgaben-Scoreboard: Custom Card unter %s registriert (Direktaufruf zum "
        "Testen im Browser möglich).",
        card_url,
    )

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
