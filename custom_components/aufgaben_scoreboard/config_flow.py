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
"""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


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
