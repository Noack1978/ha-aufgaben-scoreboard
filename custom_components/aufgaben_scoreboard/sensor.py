"""
Sensor-Plattform der Integration "Aufgaben-Punktesystem".

Erzeugt:
    - Für jeden aktiven, "echten" Home-Assistant-Benutzer (also keine
      System-/Integrations-Benutzer wie den "Home Assistant Content"-
      oder Supervisor-Benutzer) einen Sensor, dessen Zustand der
      aktuelle Punktestand ist. Als Attribute stehen die für den
      Benutzer offenen Aufgaben sowie der zuletzt erledigte Verlauf
      zur Verfügung.
    - Eine zusätzliche globale Übersichts-Entität, die ALLE offenen
      Aufgaben (unabhängig vom Benutzer) auflistet. Diese wird u. a.
      vom Sidebar-Panel für die Admin-/Gesamtübersicht verwendet.

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
    DOMAIN,
    OPTION_ENABLED_USERS,
    SIGNAL_UPDATE,
    USER_SENSOR_UNIQUE_ID_PREFIX,
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

    entitaeten: list[SensorEntity] = [AlleOffenenAufgabenSensor(manager, entry)]

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
        entitaeten.append(BenutzerPunkteSensor(manager, entry, benutzer.id, benutzer.name or benutzer.id))

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
        - erledigte_aufgaben: Die letzten erledigten Aufgaben dieses
          Benutzers (neueste zuerst).
        - user_id: Die interne Home-Assistant-Benutzer-ID (wird von der
          Custom Card benötigt, um Service-Aufrufe korrekt zuzuordnen).
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
    ) -> None:
        super().__init__(manager, entry)
        self._user_id = user_id
        self._attr_unique_id = f"{USER_SENSOR_UNIQUE_ID_PREFIX}{user_id}"
        self._attr_name = f"Punkte {anzeigename}"

    @property
    def native_value(self) -> int:
        return self._manager.get_score(self._user_id)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "user_id": self._user_id,
            "offene_aufgaben": self._manager.get_open_tasks_for_user(self._user_id),
            "erledigte_aufgaben": self._manager.get_completed_tasks_for_user(self._user_id),
        }


class AlleOffenenAufgabenSensor(_BasisSensor):
    """
    Globale Übersichts-Entität: zeigt die Gesamtzahl aller aktuell
    offenen Aufgaben als Zustand und die vollständige Aufgabenliste
    (inklusive erledigter Aufgaben, für die Admin-Ansicht) als Attribut.
    """

    _attr_icon = "mdi:format-list-checks"
    _attr_name = "Offene Aufgaben (Alle Benutzer)"
    _attr_native_unit_of_measurement = "Aufgaben"

    def __init__(self, manager: AufgabenScoreboardManager, entry: ConfigEntry) -> None:
        super().__init__(manager, entry)
        self._attr_unique_id = ALL_TASKS_SENSOR_UNIQUE_ID

    @property
    def native_value(self) -> int:
        return len(self._manager.get_all_open_tasks())

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "offene_aufgaben": self._manager.get_all_open_tasks(),
            "alle_aufgaben": self._manager.get_all_tasks(),
            "vorlagen": self._manager.get_all_templates(),
        }
