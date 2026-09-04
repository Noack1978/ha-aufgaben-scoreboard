"""
Sensor-Plattform der Integration "Aufgaben-Punktesystem".

Erzeugt:
    - Für jeden aktiven, "echten" Home-Assistant-Benutzer (also keine
      System-/Integrations-Benutzer wie den "Home Assistant Content"-
      oder Supervisor-Benutzer) einen Sensor, dessen Zustand der
      aktuelle Punktestand ist. Als Attribute stehen nur noch wenige,
      durchgehend kleine Werte zur Verfügung (siehe Docstring von
      BenutzerPunkteSensor - die früheren Listen-Attribute wurden aus
      demselben Grund wie unten beschrieben entfernt).
    - Fünf globale, REINE Zähler-Entitäten (offene Aufgaben,
      Standardaufgaben, Prämien, wartende Aufgaben-Freigaben, wartende
      Prämien-Freigaben) - jede zeigt nur eine Zahl als Zustand plus
      zwei kleine Marker-/Zeitstempel-Attribute, KEINE Listen mehr.

WICHTIG - Architekturentscheidung ab Version 2.0.0 (in einer direkten
Folgeversion auf die Benutzer-Sensoren ausgeweitet):
    Die eigentlichen (potenziell großen) Datenlisten - offene/wartende
    Aufgaben, Standardaufgaben-Vorlagen, Prämien, sowie der persönliche
    Erledigungs-/Prämien-/Punktekonto-Verlauf jedes Benutzers - stehen
    NICHT mehr als Sensor-Attribut zur Verfügung. Sie wuchsen mit der
    Zeit (mehr Vorlagen, mehr gleichzeitig offene Aufgaben, viele
    optionale Felder pro Eintrag durch Fälligkeit/Erinnerung/Trigger,
    bei aktivem Prämien-System zusätzlich lange Verlaufslisten pro
    Benutzer) über Home Assistants Grenze von 16 KB pro Zustandsattribut
    hinaus, was zu der wiederkehrenden Recorder-Warnung "State
    attributes ... exceed maximum size of 16384 bytes" führte.

    Stattdessen schreibt der Manager diese Daten als JSON-Datei nach
    config/www/aufgaben_scoreboard/daten.json (siehe
    AufgabenScoreboardManager._async_schreibe_panel_daten() sowie
    _panel_daten_snapshot() für den benutzerbezogenen Teil) - Home
    Assistant liefert den Inhalt von config/www/ automatisch und ohne
    jede eigene Registrierung unter /local/ aus, ganz ohne
    Größenbegrenzung. Das Sidebar-Panel ruft diese Datei per fetch() ab,
    sobald sich einer der fünf Zähler-Sensoren ändert - deren
    Zeitstempel-Attribut (siehe _ZaehlerSensor) wird bei WIRKLICH jeder
    Manager-Änderung neu geschrieben, unabhängig davon, ob die konkrete
    Änderung nur einen einzelnen Benutzer betrifft (z. B. dessen
    persönlicher Erledigungs-Verlauf) - ein separates Signal an den
    Benutzer-Punkte-Sensoren selbst ist dafür nicht nötig. Die Sensoren
    dienen also nur noch als leichtgewichtiges "es hat sich etwas
    geändert"-Signal, nicht mehr als Datenquelle selbst.

Alle Entitäten reagieren über den Home-Assistant-Dispatcher (Signal
SIGNAL_UPDATE) sofort auf Änderungen, die der AufgabenScoreboardManager
meldet (neue Aufgabe, Erledigung, Zuweisung etc.) - ein Polling-Intervall
wird nicht benötigt (iot_class "local_push").
"""

from __future__ import annotations

import logging

import homeassistant.util.dt as dt_util
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
        - user_id: Die interne Home-Assistant-Benutzer-ID (wird vom
          Sidebar-Panel benötigt, um Sensoren Benutzern zuzuordnen und
          Service-Aufrufe korrekt zu adressieren).
        - siege: Anzahl gewonnener Siegerehrungen (dauerhaft, übersteht
          normale Punktestand-Resets - siehe async_perform_awards()).
        - punktekonto: NUR vorhanden, wenn das Prämien-System aktiviert
          ist (siehe Options-Flow).

    WICHTIG - Architekturentscheidung seit einer weiteren, auf
    Version 2.0.0 folgenden Überarbeitung: Die früher hier vorhandenen
    fünf Listen-Attribute (offene_aufgaben, wartende_aufgaben,
    erledigte_aufgaben, eigene_praemien_verlauf, punktekonto_verlauf)
    wurden ENTFERNT. Sie waren zwar serverseitig einzeln auf 20-30
    Einträge begrenzt, konnten bei aktiver Nutzung (alle Limits
    gleichzeitig ausgeschöpft, viele Felder pro Prämien-Einlösungs-
    Eintrag durch Internet-Zeit-Felder) in Summe trotzdem wieder in die
    Nähe von bzw. über Home Assistants 16-KB-Grenze pro Zustandsattribut
    kommen - das exakt gleiche Problem wie beim früheren
    Übersichts-Sensor (siehe _ZaehlerSensor-Docstring), nur eine Ebene
    tiefer.

    Die Daten stehen seither wie folgt zur Verfügung:
        - offene_aufgaben/wartende_aufgaben: Das Panel filtert sie
          selbst aus den bereits vorhandenen GLOBALEN Listen
          (panelDaten.offene_aufgaben/wartende_aufgaben aus der JSON-
          Datei) nach user_id/assigned_to - eine separate, pro Benutzer
          duplizierte Kopie wäre reine Redundanz gewesen.
        - erledigte_aufgaben/eigene_praemien_verlauf/
          punktekonto_verlauf: stehen jetzt unter
          panelDaten.benutzer[user_id] in derselben JSON-Datei
          (siehe AufgabenScoreboardManager._panel_daten_snapshot()).
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
            "siege": self._manager.get_wins(self._user_id),
        }
        if self._praemien_aktiviert:
            attribute["punktekonto"] = self._manager.get_points_account(self._user_id)
        return attribute


class _ZaehlerSensor(_BasisSensor):
    """
    Gemeinsame Basisklasse für die fünf globalen, reinen Zähler-Sensoren
    (siehe Datei-Docstring für den architektonischen Hintergrund).

    Attribute:
        - aufgaben_scoreboard_sensor_kind: über das das Panel-JS die
          fünf Sensoren unter allen "sensor."-Entitäten zuverlässig
          unterscheiden kann, unabhängig von Sprache/Anzeigename.
        - aufgaben_scoreboard_aktualisiert_am: ein live berechneter
          Zeitstempel (siehe unten für den Hintergrund, warum das nötig
          ist).

    WICHTIG - warum der Zeitstempel nötig ist: Der Sensor-ZUSTAND ist
    bewusst eine reine Anzahl (siehe native_value der Unterklassen). Das
    allein reicht als Änderungssignal für das Panel aber NICHT aus:
    Wird eine BESTEHENDE Aufgabe/Vorlage/Prämie bearbeitet (Name,
    Beschreibung, Punktzahl, ...) oder ändert eine Aufgabe nur ihren
    Status (z. B. "offen" -> "wartet auf Freigabe"), bleibt die reine
    ANZAHL oft unverändert - das Panel würde die Änderung dann fälschlich
    für irrelevant halten und die JSON-Datei nicht neu abrufen (genau
    dieser Bug trat auf: eine Bearbeitung wurde zwar gespeichert, blieb
    im Panel aber unsichtbar, bis zufällig eine ANDERE Aktion die Anzahl
    tatsächlich veränderte). Der bei JEDEM Aufruf frisch berechnete
    Zeitstempel ändert sich dagegen bei WIRKLICH jeder Änderung - auch
    bei gleichbleibender Anzahl - und sorgt so zuverlässig für ein neues
    state_changed-Ereignis, das das Panel zum erneuten Abruf veranlasst
    (siehe _berechneZaehlerSignatur() im Panel-JS).
    """

    _attr_native_unit_of_measurement = "Stück"

    def __init__(self, manager: AufgabenScoreboardManager, entry: ConfigEntry, sensor_kind: str) -> None:
        super().__init__(manager, entry)
        self._sensor_kind = sensor_kind

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_SENSOR_KIND: self._sensor_kind,
            "aufgaben_scoreboard_aktualisiert_am": dt_util.utcnow().isoformat(),
        }


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

