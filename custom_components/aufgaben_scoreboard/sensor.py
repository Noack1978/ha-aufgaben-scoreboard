"""
Sensor-Plattform der Integration "Aufgaben-Punktesystem".

Erzeugt:
    - Für jeden aktiven, "echten" Home-Assistant-Benutzer (also keine
      System-/Integrations-Benutzer wie den "Home Assistant Content"-
      oder Supervisor-Benutzer) einen Sensor, dessen Zustand der
      aktuelle Punktestand ist. Als Attribute stehen die für den
      Benutzer offenen Aufgaben sowie der zuletzt erledigte Verlauf
      zur Verfügung (diese Listen bleiben klein/begrenzt - siehe
      manager.py, get_completed_tasks_for_user() u. Ä. - und sind
      NICHT vom unten beschriebenen Problem betroffen).
    - Fünf globale, REINE Zähler-Entitäten (offene Aufgaben,
      Standardaufgaben, Prämien, wartende Aufgaben-Freigaben, wartende
      Prämien-Freigaben) - jede zeigt nur eine Zahl als Zustand plus
      ein einziges kleines Marker-Attribut, KEINE Listen mehr.

WICHTIG - Architekturentscheidung ab Version 2.0.0:
    Die eigentlichen (potenziell großen) Datenlisten - offene/wartende
    Aufgaben, Standardaufgaben-Vorlagen, Prämien - stehen NICHT mehr
    als Sensor-Attribut zur Verfügung. Sie wuchsen mit der Zeit (mehr
    Vorlagen, mehr gleichzeitig offene Aufgaben, viele optionale Felder
    pro Eintrag durch Fälligkeit/Erinnerung/Trigger) über Home
    Assistants Grenze von 16 KB pro Zustandsattribut hinaus, was zu
    der wiederkehrenden Recorder-Warnung "State attributes ... exceed
    maximum size of 16384 bytes" führte.

    Stattdessen schreibt der Manager diese Daten als JSON-Datei nach
    config/www/aufgaben_scoreboard/daten.json (siehe
    AufgabenScoreboardManager._async_schreibe_panel_daten()) - Home
    Assistant liefert den Inhalt von config/www/ automatisch und ohne
    jede eigene Registrierung unter /local/ aus, ganz ohne
    Größenbegrenzung. Das Sidebar-Panel ruft diese Datei per fetch()
    ab und tut das genau dann erneut, wenn sich einer der fünf hier
    definierten Zähler-Sensoren ändert - die Sensoren dienen also nur
    noch als leichtgewichtiges "es hat sich etwas geändert"-Signal,
    nicht mehr als Datenquelle selbst.

Alle Entitäten reagieren über den Home-Assistant-Dispatcher (Signal
SIGNAL_UPDATE) sofort auf Änderungen, die der AufgabenScoreboardManager
meldet (neue Aufgabe, Erledigung, Zuweisung etc.) - ein Polling-Intervall
wird nicht benötigt (iot_class "local_push").
"""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ALL_TASKS_SENSOR_UNIQUE_ID,
    ATTR_SENSOR_KIND,
    DOMAIN,
    OPTION_ENABLED_USERS,
    OPTION_REWARDS_ENABLED,
    PRAEMIEN_SENSOR_UNIQUE_ID,
    SENSOR_KIND_OFFENE_AUFGABEN,
    SENSOR_KIND_PRAEMIEN,
    SENSOR_KIND_STANDARDAUFGABEN,
    SENSOR_KIND_WARTENDE_AUFGABEN,
    SENSOR_KIND_WARTENDE_PRAEMIEN,
    SIGNAL_UPDATE,
    STANDARDAUFGABEN_SENSOR_UNIQUE_ID,
    USER_SENSOR_UNIQUE_ID_PREFIX,
    WARTENDE_AUFGABEN_SENSOR_UNIQUE_ID,
    WARTENDE_PRAEMIEN_SENSOR_UNIQUE_ID,
)
from .manager import AufgabenScoreboardManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Richtet die Sensor-Entitäten beim Laden der Integration ein."""
    manager: AufgabenScoreboardManager = hass.data[DOMAIN][entry.entry_id]

    # Prämien-System ist standardmäßig deaktiviert - nur wenn im
    # Options-Flow explizit aktiviert, bekommen die Benutzer-Sensoren
    # die entsprechenden Attribute UND werden die beiden
    # Prämien-bezogenen Zähler-Sensoren überhaupt angelegt.
    praemien_aktiviert = entry.options.get(OPTION_REWARDS_ENABLED, False)

    entitaeten: list[SensorEntity] = [
        AlleOffenenAufgabenSensor(manager, entry),
        StandardaufgabenSensor(manager, entry),
        WartendeAufgabenSensor(manager, entry),
    ]
    if praemien_aktiviert:
        entitaeten.append(PraemienSensor(manager, entry))
        entitaeten.append(WartendePraemienSensor(manager, entry))

    # Welche Benutzer berücksichtigt werden, kann über den Options-Flow
    # ("Konfigurieren" bei der Integration) eingeschränkt werden - z. B.
    # um technische Benutzer/Integrations-Accounts auszublenden, die
    # zwar aktiv, aber keine echten Haushaltsmitglieder sind. Wurde die
    # Auswahl noch nie konfiguriert (Schlüssel fehlt in den Options),
    # verhält sich die Integration wie bisher und berücksichtigt ALLE
    # aktiven, nicht system-generierten Benutzer.
    erlaubte_benutzer_ids = entry.options.get(OPTION_ENABLED_USERS)

    # Für jeden "echten" Benutzer (kein System-Benutzer, aktiv, und
    # sofern konfiguriert in der Benutzerauswahl enthalten) einen
    # eigenen Punktestand-Sensor anlegen.
    alle_benutzer = await hass.auth.async_get_users()
    for benutzer in alle_benutzer:
        if benutzer.system_generated or not benutzer.is_active:
            continue
        if erlaubte_benutzer_ids is not None and benutzer.id not in erlaubte_benutzer_ids:
            continue
        entitaeten.append(
            BenutzerPunkteSensor(manager, entry, benutzer.id, benutzer.name or benutzer.id, praemien_aktiviert)
        )

    async_add_entities(entitaeten)


class _BasisSensor(SensorEntity):
    """
    Gemeinsame Basisklasse für die Sensoren dieser Integration.

    Kümmert sich um die Registrierung/Abmeldung beim Dispatcher-Signal,
    über das der Manager Änderungen bekannt gibt, sowie um die
    Zuordnung zu einem gemeinsamen "Gerät" in Home Assistant, damit alle
    Entitäten der Integration übersichtlich gruppiert dargestellt werden.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: AufgabenScoreboardManager, entry: ConfigEntry) -> None:
        self._manager = manager
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Aufgaben-Punktesystem",
            manufacturer="Eigene Integration",
            model="Aufgaben-Scoreboard",
            entry_type="service",
        )

    async def async_added_to_hass(self) -> None:
        """Beim Hinzufügen der Entität auf Datenänderungen abonnieren."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._auf_update_reagieren)
        )

    def _auf_update_reagieren(self) -> None:
        """
        Wird vom Dispatcher aufgerufen, sobald sich Daten geändert haben.

        WICHTIG: async_write_ha_state() darf ausschließlich im Event-Loop-
        Thread aufgerufen werden. Da sich in der Praxis nicht mit letzter
        Sicherheit vorhersagen lässt, aus welchem Thread heraus der
        Dispatcher diese Methode letztlich aufruft (abhängig davon, wie
        Home Assistant den ursprünglich auslösenden Service-Aufruf
        intern einplant), wird der eigentliche Zustands-Update-Aufruf
        hier direkt über hass.loop.call_soon_threadsafe() eingeplant.
        Das garantiert IMMER die korrekte Ausführung im Event-Loop-
        Thread, unabhängig davon, von wo aus _auf_update_reagieren
        selbst aufgerufen wurde.
        """
        self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)


class BenutzerPunkteSensor(_BasisSensor):
    """
    Ein Sensor pro Home-Assistant-Benutzer.

    Zustand: aktueller Punktestand (Ganzzahl).
    Attribute:
        - offene_aufgaben: Liste der für diesen Benutzer offenen Aufgaben
          (explizit zugewiesen oder für alle freigegeben).
        - wartende_aufgaben: Aufgaben, die dieser Benutzer selbst als
          erledigt gemeldet hat und die noch auf Admin-Freigabe warten.
        - erledigte_aufgaben: Die letzten erledigten (freigegebenen)
          Aufgaben dieses Benutzers (neueste zuerst), jeweils mit einem
          "ruecknehmbar"-Flag für die Rücknahme-Funktion.
        - siege: Anzahl gewonnener Siegerehrungen (dauerhaft, übersteht
          normale Punktestand-Resets - siehe async_perform_awards()).
        - punktekonto / eigene_praemien_verlauf / punktekonto_verlauf:
          NUR vorhanden, wenn das Prämien-System aktiviert ist (siehe
          Options-Flow). punktekonto_verlauf enthält die einzelnen
          Zugänge (Siegerehrung) und Abgänge (Prämien-Einlösung).
        - user_id: Die interne Home-Assistant-Benutzer-ID (wird vom
          Sidebar-Panel benötigt, um Sensoren Benutzern zuzuordnen und
          Service-Aufrufe korrekt zu adressieren).

    WICHTIG: Diese personenbezogenen Listen bleiben - anders als die
    fünf globalen Zähler-Sensoren unten - weiterhin echte Attribute.
    Sie sind serverseitig bereits auf 20-30 Einträge begrenzt (siehe
    manager.py) und waren nie Teil des 16-KB-Problems.
    """

    _attr_icon = "mdi:star-check-outline"
    _attr_native_unit_of_measurement = "Punkte"
    _attr_state_class = "total"

    def __init__(
        self,
        manager: AufgabenScoreboardManager,
        entry: ConfigEntry,
        user_id: str,
        anzeigename: str,
        praemien_aktiviert: bool = False,
    ) -> None:
        super().__init__(manager, entry)
        self._user_id = user_id
        self._praemien_aktiviert = praemien_aktiviert
        self._attr_unique_id = f"{USER_SENSOR_UNIQUE_ID_PREFIX}{user_id}"
        self._attr_name = f"Punkte {anzeigename}"

    @property
    def native_value(self) -> int:
        return self._manager.get_score(self._user_id)

    @property
    def extra_state_attributes(self) -> dict:
        attribute = {
            "user_id": self._user_id,
            "offene_aufgaben": self._manager.get_open_tasks_for_user(self._user_id),
            "wartende_aufgaben": self._manager.get_pending_tasks_for_user(self._user_id),
            "erledigte_aufgaben": self._manager.get_completed_tasks_for_user(self._user_id),
            "siege": self._manager.get_wins(self._user_id),
        }
        if self._praemien_aktiviert:
            attribute["punktekonto"] = self._manager.get_points_account(self._user_id)
            attribute["eigene_praemien_verlauf"] = self._manager.get_redemptions_for_user(self._user_id)
            attribute["punktekonto_verlauf"] = self._manager.get_points_history_for_user(self._user_id)
        return attribute


class _ZaehlerSensor(_BasisSensor):
    """
    Gemeinsame Basisklasse für die fünf globalen, reinen Zähler-Sensoren
    (siehe Datei-Docstring für den architektonischen Hintergrund).

    Jeder Zähler-Sensor hat außer der Anzahl NUR EIN Attribut -
    "aufgaben_scoreboard_sensor_kind" - über das das Panel-JS die fünf
    Sensoren unter allen "sensor."-Entitäten zuverlässig unterscheiden
    kann, unabhängig von Sprache/Anzeigename der jeweiligen Entität.
    """

    _attr_native_unit_of_measurement = "Stück"

    def __init__(self, manager: AufgabenScoreboardManager, entry: ConfigEntry, sensor_kind: str) -> None:
        super().__init__(manager, entry)
        self._sensor_kind = sensor_kind

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_SENSOR_KIND: self._sensor_kind}


class AlleOffenenAufgabenSensor(_ZaehlerSensor):
    """Zeigt die Anzahl aller aktuell offenen Aufgaben (unabhängig vom Benutzer)."""

    _attr_icon = "mdi:format-list-checks"
    _attr_name = "Offene Aufgaben (Alle Benutzer)"

    def __init__(self, manager: AufgabenScoreboardManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, SENSOR_KIND_OFFENE_AUFGABEN)
        self._attr_unique_id = ALL_TASKS_SENSOR_UNIQUE_ID

    @property
    def native_value(self) -> int:
        return len(self._manager.get_all_open_tasks())


class StandardaufgabenSensor(_ZaehlerSensor):
    """Zeigt die Anzahl konfigurierter Standardaufgaben (Vorlagen)."""

    _attr_icon = "mdi:repeat"
    _attr_name = "Standardaufgaben"

    def __init__(self, manager: AufgabenScoreboardManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, SENSOR_KIND_STANDARDAUFGABEN)
        self._attr_unique_id = STANDARDAUFGABEN_SENSOR_UNIQUE_ID

    @property
    def native_value(self) -> int:
        return len(self._manager.get_all_templates())


class PraemienSensor(_ZaehlerSensor):
    """Zeigt die Anzahl konfigurierter Prämien. Nur angelegt, wenn das Prämien-System aktiviert ist."""

    _attr_icon = "mdi:gift"
    _attr_name = "Prämien"

    def __init__(self, manager: AufgabenScoreboardManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, SENSOR_KIND_PRAEMIEN)
        self._attr_unique_id = PRAEMIEN_SENSOR_UNIQUE_ID

    @property
    def native_value(self) -> int:
        return len(self._manager.get_all_rewards())


class WartendeAufgabenSensor(_ZaehlerSensor):
    """Zeigt die Anzahl der Aufgaben, die aktuell auf Admin-Freigabe warten (alle Benutzer)."""

    _attr_icon = "mdi:clock-alert-outline"
    _attr_name = "Wartende Aufgaben"

    def __init__(self, manager: AufgabenScoreboardManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, SENSOR_KIND_WARTENDE_AUFGABEN)
        self._attr_unique_id = WARTENDE_AUFGABEN_SENSOR_UNIQUE_ID

    @property
    def native_value(self) -> int:
        return len(self._manager.get_all_pending_tasks())


class WartendePraemienSensor(_ZaehlerSensor):
    """Zeigt die Anzahl der Prämien-Einlösungen, die aktuell auf Admin-Freigabe warten. Nur bei aktiviertem Prämien-System."""

    _attr_icon = "mdi:clock-alert-outline"
    _attr_name = "Wartende Prämien"

    def __init__(self, manager: AufgabenScoreboardManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry, SENSOR_KIND_WARTENDE_PRAEMIEN)
        self._attr_unique_id = WARTENDE_PRAEMIEN_SENSOR_UNIQUE_ID

    @property
    def native_value(self) -> int:
        return len(self._manager.get_pending_redemptions())

