# 🏆 Aufgaben-Punktesystem für Home Assistant

Eine benutzerdefinierte Home-Assistant-Integration, mit der du manuell
Aufgaben (Chores) für die Benutzer deines HA-Servers anlegen kannst.
Jede Aufgabe hat einen festen Punktwert. Benutzer erledigen Aufgaben,
um Punkte zu sammeln – Aufgaben können außerdem gezielt bestimmten
Benutzern zugewiesen werden.

## ✨ Funktionen

- **Aufgaben manuell anlegen** mit Titel, Beschreibung und Punktwert
- **Manuelle Zuweisung** von Aufgaben an bestimmte Benutzer (oder offen
  für alle)
- **Punktestand pro Benutzer** als eigene Sensor-Entität
  (`sensor.punkte_<benutzername>`)
- **Eigenes Sidebar-Panel** ("Aufgaben") in der Seitenleiste mit
  vollständiger Verwaltung (Anlegen, Zuweisen, Löschen – nur für
  Administratoren) sowie einer Rangliste aller Benutzer
- **Custom Card** (`custom:aufgaben-scoreboard-card`), die in jedem
  beliebigen Dashboard platziert werden kann und die eigenen offenen
  Aufgaben samt "Erledigt"-Button zeigt
- **Services** für Automationen/Skripte: `add_task`, `remove_task`,
  `assign_task`, `unassign_task`, `complete_task`, `reset_score`
- Daten werden lokal in der Home-Assistant-Storage gespeichert – keine
  Cloud, keine externen Abhängigkeiten

## 📦 Installation

### Variante A: Manuell

1. Lade die neueste Version als ZIP aus den
   [Releases](../../releases) herunter (oder klone das Repository).
2. Kopiere den Ordner `custom_components/aufgaben_scoreboard` in das
   Verzeichnis `custom_components` deiner Home-Assistant-Konfiguration
   (falls der Ordner `custom_components` noch nicht existiert, lege ihn
   im selben Verzeichnis wie `configuration.yaml` an).
3. Die Ordnerstruktur muss danach so aussehen:

   ```
   config/
   └── custom_components/
       └── aufgaben_scoreboard/
           ├── __init__.py
           ├── manifest.json
           ├── ...
           └── frontend/
               ├── aufgaben-scoreboard-card.js
               └── aufgaben-scoreboard-panel.js
   ```

4. Home Assistant **neu starten**.
5. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen**
   nach **"Aufgaben-Punktesystem"** suchen und hinzufügen.

### Variante B: Über HACS (empfohlen)

1. In HACS unter **Integrationen → Menü (⋮) → Benutzerdefinierte
   Repositories** dieses GitHub-Repository als Typ **Integration**
   hinzufügen.
2. Die Integration "Aufgaben-Punktesystem" installieren.
3. Home Assistant neu starten und wie oben über **Einstellungen →
   Geräte & Dienste** hinzufügen.

Nach der Einrichtung erscheinen automatisch:

- ein neuer Eintrag **"Aufgaben"** in der Seitenleiste,
- die Custom Card `custom:aufgaben-scoreboard-card` zur Verwendung in
  eigenen Dashboards.

## 🖥️ Nutzung

### Sidebar-Panel "Aufgaben"

Zeigt für **alle Benutzer** eine Rangliste der Punktestände. Im
Abschnitt "Meine offenen Aufgaben" kann jeder Benutzer seine eigenen
Aufgaben abhaken. **Administratoren** sehen zusätzlich den
Verwaltungsbereich, in dem neue Aufgaben angelegt, bestehende Aufgaben
zusätzlichen Benutzern zugewiesen oder gelöscht werden können.

### Custom Card im Dashboard

Über den Dashboard-Editor eine neue Karte hinzufügen und
`Aufgaben-Scoreboard Karte` auswählen, oder per YAML:

```yaml
type: custom:aufgaben-scoreboard-card
```

Die Karte benötigt keine weitere Konfiguration – sie erkennt den
angemeldeten Benutzer automatisch.

### Aufgaben per Automation/Skript anlegen

```yaml
service: aufgaben_scoreboard.add_task
data:
  name: "Müll rausbringen"
  description: "Restmüll und Papiertonne an die Straße stellen"
  score: 5
  assigned_to:
    - "3f8b2c1a9d4e4f6a8b7c6d5e4f3a2b1c"   # Home-Assistant-Benutzer-ID
```

Die Benutzer-ID findest du z. B. in den Attributen der jeweiligen
Punkte-Sensor-Entität (`user_id`) oder unter **Einstellungen →
Personen → Benutzer**.

### Verfügbare Services im Überblick

| Service                          | Beschreibung                                          | Nur Admin |
|-----------------------------------|--------------------------------------------------------|-----------|
| `aufgaben_scoreboard.add_task`      | Neue Aufgabe anlegen                                   | ✅        |
| `aufgaben_scoreboard.remove_task`   | Aufgabe löschen                                        | ✅        |
| `aufgaben_scoreboard.assign_task`   | Aufgabe einem Benutzer zuweisen                        | ✅        |
| `aufgaben_scoreboard.unassign_task` | Zuweisung eines Benutzers entfernen                    | ✅        |
| `aufgaben_scoreboard.complete_task` | Aufgabe als erledigt markieren, Punkte gutschreiben     | Nein¹     |
| `aufgaben_scoreboard.reset_score`   | Punktestand eines Benutzers auf 0 zurücksetzen          | ✅        |

¹ Jeder Benutzer darf nur seine eigenen Aufgaben erledigen;
Administratoren dürfen dies stellvertretend für jeden Benutzer tun.

## 🗂️ Datenspeicherung

Alle Aufgaben, Zuweisungen, Punktestände und der Erledigungsverlauf
werden lokal über den Home-Assistant-eigenen Storage-Mechanismus in
`.storage/aufgaben_scoreboard_data` gespeichert. Ein Backup dieser
Datei sichert den gesamten Zustand der Integration.

## 🛠️ Entwicklung / Aufbau des Codes

```
custom_components/aufgaben_scoreboard/
├── __init__.py         # Setup, Services, Frontend-Registrierung
├── config_flow.py      # Einrichtungsdialog über die HA-UI
├── const.py             # Zentrale Konstanten
├── manager.py           # Datenlogik (Aufgaben, Punkte, Speicherung)
├── manifest.json         # Metadaten der Integration
├── sensor.py             # Sensor-Entitäten (Punktestände, Übersicht)
├── services.yaml         # Service-Beschreibungen für die HA-UI
├── strings.json / translations/  # Übersetzungen
└── frontend/
    ├── aufgaben-scoreboard-card.js    # Custom Card fürs Dashboard
    └── aufgaben-scoreboard-panel.js   # Sidebar-Panel (volle Verwaltung)
```

Der komplette Code ist ausführlich auf Deutsch kommentiert und
dokumentiert, um Anpassungen und das Verständnis zu erleichtern.

## 📄 Lizenz

Dieses Projekt kann z. B. unter der MIT-Lizenz veröffentlicht werden –
füge dazu eine `LICENSE`-Datei mit dem gewünschten Lizenztext hinzu.

## 🤝 Mitwirken

Issues und Pull Requests sind willkommen! Bitte beschreibe
Fehlerberichte möglichst genau (Home-Assistant-Version, Logauszug aus
**Einstellungen → System → Protokolle**).
