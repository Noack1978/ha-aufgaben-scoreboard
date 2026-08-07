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
- **Standardaufgaben (Vorlagen)** für wiederkehrende Aufgaben, inkl.
  **Multiscoring** (eigene Aufgabe pro zugewiesenem Benutzer) sowie
  automatischer Anlage per **Entitäts-Trigger** und/oder **Zeitplan**
  (alle X Tage oder wöchentlich an einem festen Wochentag)
- **Services** für Automationen/Skripte: `add_task`, `update_task`,
  `remove_task`, `assign_task`, `unassign_task`, `complete_task`,
  `reset_score`, `add_template`, `update_template`, `remove_template`,
  `create_task_from_template`
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
über "Bearbeiten" nachträglich geändert (inkl. Titel, Beschreibung,
Punkte und Zuständigkeit) oder gelöscht werden können. Die Zuständigkeit
wird dabei per Checkbox-Liste ausgewählt – mehrere Benutzer lassen sich
so auf einen Blick erkennen, gezielt hinzufügen und auch wieder
abwählen.

### Berücksichtigte Benutzer konfigurieren

Standardmäßig bekommt jeder aktive, nicht-technische Home-Assistant-
Benutzer einen eigenen Punkte-Sensor und steht in der
Zuständigkeits-Auswahl zur Verfügung. Über **Einstellungen → Geräte &
Dienste → Aufgaben-Punktesystem → Konfigurieren** lässt sich per
Checkbox-Liste gezielt einschränken, welche Benutzer berücksichtigt
werden – z. B. um technische Benutzer/Integrations-Accounts
auszublenden. Die Änderung wird sofort wirksam (die Integration lädt
sich automatisch neu).

### Standardaufgaben (Vorlagen)

Im Verwaltungsbereich gibt es einen eigenen Abschnitt „Standardaufgaben“
für wiederkehrende Aufgaben, die nicht jedes Mal neu angelegt werden
sollen (z. B. „Rasen mähen“, „Mülleimer rausbringen“). Eine
Standardaufgabe legt Titel, Beschreibung, Punkte und Zuständigkeit
einmalig fest; konkrete, erledigbare Aufgaben lassen sich daraus
beliebig oft erzeugen:

- **Manuell**: Button „Jetzt anlegen“ bei der jeweiligen Standardaufgabe.
- **Automatisch per Entitäts-Trigger**: über eine optionale Entität +
  Ziel-Zustand direkt im Formular (mit derselben Entitäts-/
  Zustands-Auswahl wie im Automationen-Editor). Sobald die gewählte
  Entität den Zielwert erreicht, wird automatisch eine Aufgabe angelegt
  – aber nur, wenn nicht bereits eine offene Aufgabe aus derselben
  Vorlage existiert (Duplikat-Schutz).
- **Automatisch per Zeitplan**: unabhängig vom Entitäts-Trigger (auch
  gleichzeitig mit ihm nutzbar) lässt sich eine Standardaufgabe so
  konfigurieren, dass sie
  - **alle X Tage** (z. B. alle 3 Tage), oder
  - **wöchentlich an einem festen Wochentag** (jede Woche oder alle X
    Wochen)

  automatisch eine neue Aufgabe erzeugt. Die Prüfung läuft täglich um
  00:05 Uhr sowie einmalig direkt beim Start von Home Assistant (damit
  ein fälliger Tag nicht übersehen wird, falls HA um 00:05 Uhr gerade
  nicht lief). Doppelte Anlage wird zweifach verhindert: zum einen darf
  am selben Tag nur einmal ausgelöst werden, zum anderen greift –
  genau wie beim Entitäts-Trigger – der Schutz, dass keine neue Aufgabe
  entsteht, solange aus derselben Vorlage noch eine offene existiert.

**Multiscoring**: Ist diese Option bei einer Standardaufgabe aktiviert,
entsteht beim Anlegen für **jeden zugewiesenen Benutzer eine eigene,
unabhängig erledigbare Aufgabe** (statt einer gemeinsamen) – jeder kann
so eigene Punkte sammeln. Erfordert mindestens einen zugewiesenen
Benutzer. In der Übersicht erscheint dadurch pro Benutzer eine eigene
Karte; erledigt jemand seine, verschwindet nur diese – die Aufgaben der
übrigen zugewiesenen Benutzer bleiben unberührt bestehen.

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
| `aufgaben_scoreboard.update_task`   | Bestehende Aufgabe nachträglich bearbeiten             | ✅        |
| `aufgaben_scoreboard.remove_task`   | Aufgabe löschen                                        | ✅        |
| `aufgaben_scoreboard.assign_task`   | Aufgabe einem Benutzer zuweisen                        | ✅        |
| `aufgaben_scoreboard.unassign_task` | Zuweisung eines Benutzers entfernen                    | ✅        |
| `aufgaben_scoreboard.complete_task` | Aufgabe als erledigt markieren, Punkte gutschreiben     | Nein¹     |
| `aufgaben_scoreboard.reset_score`   | Punktestand eines Benutzers auf 0 zurücksetzen          | ✅        |
| `aufgaben_scoreboard.add_template`  | Standardaufgabe (Vorlage) anlegen, optional mit Entitäts- und/oder Zeitplan-Trigger | ✅        |
| `aufgaben_scoreboard.update_template` | Standardaufgabe nachträglich bearbeiten               | ✅        |
| `aufgaben_scoreboard.remove_template` | Standardaufgabe löschen                               | ✅        |
| `aufgaben_scoreboard.create_task_from_template` | Aufgabe(n) aus einer Standardaufgabe anlegen | ✅        |

¹ Jeder Benutzer darf nur seine eigenen Aufgaben erledigen;
Administratoren dürfen dies stellvertretend für jeden Benutzer tun.

## ⚠️ Bekanntes Problem: Custom Card verschwindet aus der Kartenauswahl (browser_mod)

Wenn parallel die Integration [`browser_mod`](https://github.com/thomasloven/hass-browser_mod)
installiert ist, kann die Custom Card in der „Zum Dashboard
hinzufügen"-Auswahl mit einem endlosen Ladekreis hängen bleiben bzw.
danach nicht mehr auffindbar sein, bis das Dashboard hart neu geladen
wird. Betroffen kann dabei jede beliebige Custom Card sein, nicht nur
diese Integration.

**Ursache ist ein bestätigter Fehler in `browser_mod` selbst** (nicht in
dieser Integration): Dessen Polyfill für „scoped custom element
registries" bringt Home Assistants eigene Kartenauswahl beim Erzeugen
einer Fehleranzeige durcheinander
(`TypeError: Illegal constructor ...`, siehe
[hass-browser_mod#1056](https://github.com/thomasloven/hass-browser_mod/issues/1056)).
Die Registrierung dieser Integration selbst ist davon nicht betroffen –
im Log erscheinen bei erfolgreichem Start weiterhin diese Zeilen:

```
INFO ... Aufgaben-Scoreboard: Custom Card unter .../aufgaben-scoreboard-card.js registriert ...
INFO ... Aufgaben-Scoreboard: Sidebar-Panel unter '/aufgaben-scoreboard' registriert.
```

**Workaround:** Dashboard-Seite hart neu laden (nicht nur die
Integration neu laden), oder testweise `browser_mod` kurzzeitig
deaktivieren, um zu bestätigen, dass es sich um dieses bekannte Problem
handelt. Ein Fix müsste in `browser_mod` selbst erfolgen; der oben
verlinkte Issue kann zur Verfolgung des Status beobachtet werden.

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
