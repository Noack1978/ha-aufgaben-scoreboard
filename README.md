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
- **Aufgaben-Übersicht im Dashboard** über eine native Markdown-Karte
  (Vorlage weiter unten) – ohne Custom Element, dadurch ohne die
  Kompatibilitätsprobleme, die eine frühere Custom Card mit sich
  brachte (siehe Abschnitt weiter unten)
- **Freigabe-Workflow**: Erledigungen warten auf Bestätigung durch einen
  Administrator, bevor Punkte gutgeschrieben werden – inkl. Verlauf pro
  Benutzer und nachträglicher Rücknahme-Möglichkeit (zeitlich/mengenmäßig
  begrenzt)
- **Standardaufgaben (Vorlagen)** für wiederkehrende Aufgaben, inkl.
  **Multiscoring** (eigene Aufgabe pro zugewiesenem Benutzer) sowie
  automatischer Anlage per **Entitäts-Trigger** und/oder **Zeitplan**
  (alle X Tage oder wöchentlich an einem festen Wochentag)
- **Services** für Automationen/Skripte: `add_task`, `update_task`,
  `remove_task`, `assign_task`, `unassign_task`, `complete_task`,
  `approve_task`, `reject_task`, `undo_completion`, `reset_score`,
  `add_template`, `update_template`, `remove_template`,
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

Nach der Einrichtung erscheint automatisch ein neuer Eintrag
**"Aufgaben"** in der Seitenleiste. Für eine Aufgaben-Übersicht direkt
im Dashboard siehe den Abschnitt "Aufgaben im Dashboard anzeigen"
weiter unten.

## 🖥️ Nutzung

### Sidebar-Panel "Aufgaben"

Zeigt für **alle Benutzer** eine Rangliste der Punktestände. Ein Klick
auf einen Namen klappt dessen Erledigungs-Verlauf auf. Im Abschnitt
"Meine offenen Aufgaben" kann jeder Benutzer seine eigenen Aufgaben als
erledigt melden – die Punkte werden dabei **nicht sofort** gutgeschrieben
(siehe nächster Abschnitt). **Administratoren** sehen zusätzlich den
Verwaltungsbereich, in dem neue Aufgaben angelegt, bestehende Aufgaben
über "Bearbeiten" nachträglich geändert (inkl. Titel, Beschreibung,
Punkte und Zuständigkeit) oder gelöscht werden können. Die Zuständigkeit
wird dabei per Checkbox-Liste ausgewählt – mehrere Benutzer lassen sich
so auf einen Blick erkennen, gezielt hinzufügen und auch wieder
abwählen.

### Freigabe-Workflow: Erledigung prüfen, bevor Punkte gutgeschrieben werden

Meldet ein Benutzer eine Aufgabe als erledigt, wird sie **nicht sofort**
abgeschlossen, sondern wechselt in den Status „wartet auf Freigabe" –
ohne Punktegutschrift. Das gilt einheitlich für **alle** Benutzer, auch
für Administratoren selbst.

Administratoren sehen im Verwaltungsbereich einen eigenen Abschnitt
„⏳ Wartet auf Freigabe" mit allen offenen Meldungen (wer, wann, welche
Aufgabe) und zwei Buttons:

- **Freigeben**: Aufgabe gilt als erledigt, Punkte werden jetzt
  gutgeschrieben, der Eintrag erscheint im Verlauf.
- **Ablehnen**: keine Punkte, Aufgabe wird wieder offen und kann erneut
  erledigt werden (z. B. falls sie nicht ordentlich gemacht wurde).

**Verlauf & nachträgliche Rücknahme:** Ein Klick auf einen Benutzernamen
in der Rangliste zeigt dessen zuletzt freigegebene Aufgaben mit Datum
und Punkten. Administratoren können dort per „Rückgängig" eine bereits
freigegebene Erledigung nachträglich zurücknehmen (z. B. bei irrtümlicher
Freigabe) – die Punkte werden abgezogen und die Aufgabe wieder geöffnet.
Das ist aus zwei Gründen begrenzt: nur innerhalb der letzten **7 Tage**
und nur unter den letzten **20 Erledigungen** desselben Benutzers. Ältere
Einträge werden im Verlauf weiterhin angezeigt, aber ohne
„Rückgängig"-Button.

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

### Aufgaben im Dashboard anzeigen (Markdown-Karte)

Es gab bis Version 1.4.0 eine eigene Custom Card
(`custom:aufgaben-scoreboard-card`) für normale Dashboards. Sie wurde
entfernt, nachdem sie wiederholt - trotz mehrerer gezielter Fixes - im
Kartenauswahl-Dialog mit `Custom element doesn't exist` bzw. einem
endlos hängenden Ladekreis fehlschlug. Die genaue Ursache ließ sich
trotz umfangreicher Diagnose (Log-Analyse, Ausschluss von `browser_mod`
und `lovelace-header-cards` als Auslöser) nicht abschließend klären.

Stattdessen lässt sich eine Übersicht aller offenen Aufgaben mit einer
**nativen Markdown-Karte** abbilden - kein Custom Element, keine
zusätzliche JavaScript-Registrierung, dadurch von den oben genannten
Problemen nicht betroffen. Neue Karte → **Markdown** → in den
YAML-Modus wechseln und folgenden Code einfügen:

```yaml
type: markdown
title: 📋 Alle offenen Aufgaben
content: |
  {% set aufgaben = state_attr('sensor.aufgaben_punktesystem_offene_aufgaben_alle_benutzer', 'offene_aufgaben') %}
  {% set benutzer_sensoren = states.sensor | selectattr('attributes.user_id', 'defined') | list %}
  {%- if not aufgaben %}
  Aktuell keine offenen Aufgaben. 🎉
  {%- else %}
  **{{ aufgaben | length }} offene Aufgabe(n)**

  | Aufgabe | Punkte | Zuständig |
  | --- | --- | --- |
  {% for aufgabe in aufgaben | sort(attribute='name') -%}
  {%- set ns = namespace(namen=[]) -%}
  {%- for uid in aufgabe.assigned_to -%}
  {%- for b in benutzer_sensoren -%}
  {%- if b.attributes.user_id == uid -%}
  {%- set ns.namen = ns.namen + [b.name] -%}
  {%- endif -%}
  {%- endfor -%}
  {%- endfor -%}
  | {{ aufgabe.name }}{% if aufgabe.description %} ({{ aufgabe.description }}){% endif %} | +{{ aufgabe.score }} | {{ ns.namen | join(', ') if ns.namen else 'Alle Benutzer' }} |
  {% endfor -%}
  {%- endif %}
```

**Hinweis zur Entity-ID:** `sensor.aufgaben_punktesystem_offene_aufgaben_alle_benutzer`
ist die Entity-ID des Übersichts-Sensors. Falls sie bei dir abweicht
(z. B. durch ein Namenskollisions-Suffix), in **Entwicklerwerkzeuge →
Zustände** nach "Offene Aufgaben" suchen und die erste Zeile im obigen
Code entsprechend anpassen.

**Optional - Spaltenbreiten anpassen:** Falls [`card_mod`](https://github.com/thomasloven/lovelace-card-mod)
installiert ist, lässt sich die Tabellenbreite pro Spalte festlegen:

```yaml
card_mod:
  style:
    ha-markdown$: |
      table {
        table-layout: fixed;
        width: 100%;
      }
      th:nth-child(1), td:nth-child(1) { width: 55%; }
      th:nth-child(2), td:nth-child(2) { width: 15%; }
      th:nth-child(3), td:nth-child(3) { width: 30%; }
```

Die Prozentwerte nach Bedarf anpassen (sollten zusammen ~100% ergeben).

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
| `aufgaben_scoreboard.complete_task` | Aufgabe als erledigt melden (wartet danach auf Freigabe, noch keine Punkte) | Nein¹ |
| `aufgaben_scoreboard.approve_task`  | Erledigung freigeben, Punkte werden jetzt gutgeschrieben | ✅        |
| `aufgaben_scoreboard.reject_task`   | Erledigung ablehnen, Aufgabe wird wieder offen          | ✅        |
| `aufgaben_scoreboard.undo_completion` | Bereits freigegebene Erledigung nachträglich zurücknehmen (Grenzen: 7 Tage / letzte 20 Einträge) | ✅ |
| `aufgaben_scoreboard.reset_score`   | Punktestand eines Benutzers auf 0 zurücksetzen (löscht dabei auch dessen Erledigungs-Historie) | ✅ |
| `aufgaben_scoreboard.add_template`  | Standardaufgabe (Vorlage) anlegen, optional mit Entitäts- und/oder Zeitplan-Trigger | ✅        |
| `aufgaben_scoreboard.update_template` | Standardaufgabe nachträglich bearbeiten               | ✅        |
| `aufgaben_scoreboard.remove_template` | Standardaufgabe löschen                               | ✅        |
| `aufgaben_scoreboard.create_task_from_template` | Aufgabe(n) aus einer Standardaufgabe anlegen | ✅        |

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
