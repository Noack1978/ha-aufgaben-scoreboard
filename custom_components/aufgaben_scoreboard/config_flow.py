"""
Config Flow der Integration "Aufgaben-Punktesystem".

Diese Integration benötigt keinerlei Verbindungsdaten (kein API-Key,
keine IP-Adresse o. Ä.) - sie verwaltet ihre Daten komplett lokal.
Der Config Flow besteht daher nur aus einem einzigen Bestätigungsschritt
("Integration hinzufügen" -> "Absenden"), der einen Config-Entry
anlegt. Danach übernimmt __init__.py das eigentliche Setup.

Da in manifest.json "single_config_entry": true gesetzt ist, verhindert
Home Assistant automatisch, dass die Integration mehrfach eingerichtet
wird.

Zusätzlich stellt diese Datei den Options-Flow bereit
(AufgabenScoreboardOptionsFlow): Darüber lässt sich nachträglich (über
"Einstellungen -> Geräte & Dienste -> Aufgaben-Punktesystem ->
Konfigurieren") auswählen, welche Home-Assistant-Benutzer von der
Integration berücksichtigt werden sollen - also einen eigenen
Punkte-Sensor bekommen und in den Zuweisungslisten (neue Aufgabe
anlegen/bearbeiten) auswählbar sind. Damit lassen sich z. B. technische
Benutzer/Integrations-Accounts gezielt ausblenden. Zusätzlich lässt sich
dort das optionale Prämien-System (Punktekonto + einlösbare Prämien)
ein-/ausschalten - standardmäßig deaktiviert.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import DOMAIN, OPTION_ENABLED_USERS, OPTION_REWARDS_ENABLED


class AufgabenScoreboardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Behandelt den Einrichtungs-Dialog dieser Integration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """
        Erster (und einziger) Schritt der Einrichtung.

        Da keine Eingaben vom Benutzer benötigt werden, wird beim ersten
        Aufruf direkt der Bestätigungs-Schritt angezeigt; bestätigt der
        Benutzer, wird sofort der Config-Entry erstellt.
        """
        # Sicherstellen, dass die Integration nicht doppelt eingerichtet wird.
        self._async_abort_entries_match()

        if user_input is not None:
            return self.async_create_entry(title="Aufgaben-Punktesystem", data={})

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AufgabenScoreboardOptionsFlow:
        """Liefert den Options-Flow-Handler dieser Integration."""
        return AufgabenScoreboardOptionsFlow()


class AufgabenScoreboardOptionsFlow(OptionsFlowWithReload):
    """
    Options-Flow zur nachträglichen Auswahl der berücksichtigten Benutzer.

    Wichtig: Diese Klasse darf KEIN __init__ definieren, das
    self.config_entry setzt (führt seit HA 2025.12 zu einem
    AttributeError) - self.config_entry wird von OptionsFlowWithReload
    bereits automatisch bereitgestellt. Wird die Auswahl gespeichert,
    lädt OptionsFlowWithReload die Integration automatisch neu, sodass
    die Sensor-Plattform sofort mit der neuen Benutzerauswahl reagiert.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Einziger Schritt: Mehrfachauswahl der berücksichtigten Benutzer + Prämien-System ein-/ausschalten."""
        alle_benutzer = [
            benutzer
            for benutzer in await self.hass.auth.async_get_users()
            if not benutzer.system_generated and benutzer.is_active
        ]
        gueltige_ids = {benutzer.id for benutzer in alle_benutzer}

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    OPTION_ENABLED_USERS: user_input[OPTION_ENABLED_USERS],
                    OPTION_REWARDS_ENABLED: user_input.get(OPTION_REWARDS_ENABLED, False),
                },
            )

        # Vorbelegung: bisherige Auswahl aus den Options, oder - falls die
        # Integration noch nie konfiguriert wurde - ALLE aktuell
        # vorhandenen Benutzer (entspricht dem bisherigen Verhalten ohne
        # Filterung, damit sich beim ersten Öffnen nichts unerwartet
        # ändert).
        bisherige_auswahl = self.config_entry.options.get(
            OPTION_ENABLED_USERS, list(gueltige_ids)
        )
        # Zwischenzeitlich gelöschte/deaktivierte Benutzer aus der
        # Vorbelegung entfernen, damit der Selector keine "verwaisten"
        # Werte anzeigt.
        vorbelegung = [uid for uid in bisherige_auswahl if uid in gueltige_ids]
        praemien_vorbelegung = self.config_entry.options.get(OPTION_REWARDS_ENABLED, False)

        schema = vol.Schema(
            {
                vol.Required(OPTION_ENABLED_USERS, default=vorbelegung): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=benutzer.id, label=benutzer.name or benutzer.id)
                            for benutzer in alle_benutzer
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(OPTION_REWARDS_ENABLED, default=praemien_vorbelegung): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
