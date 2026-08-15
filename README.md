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
- **Custom Card** (`custom:aufgaben-scoreboard-card`) für die eigenen
  offenen Aufgaben direkt in einem beliebigen Dashboard, sowie
  alternativ eine native **Markdown-Karte** (Vorlage weiter unten) für
  die Übersicht aller offenen Aufgaben ohne Custom Element
- **Freigabe-Workflow**: Erledigungen warten auf Bestätigung durch einen
  Administrator, bevor Punkte gutgeschrieben werden – inkl. Verlauf pro
  Benutzer und nachträglicher Rücknahme-Möglichkeit (zeitlich/mengenmäßig
  begrenzt)
- **Standardaufgaben (Vorlagen)** für wiederkehrende Aufgaben, inkl.
  **Multiscoring** (eigene Aufgabe pro zugewiesenem Benutzer) sowie
  automatischer Anlage per **Entitäts-Trigger** und/oder **Zeitplan**
  (alle X Tage oder wöchentlich an einem festen Wochentag)
- **Siegerehrung**: ermittelt den/die Benutzer mit dem höchsten
  Punktestand (dauerhafter Sieg-Zähler pro Benutzer) und setzt
  anschließend alle Punktestände für eine neue Runde zurück
- **Prämien-System** (optional aktivierbar): Punktekonto, das bei der
  Siegerehrung gespeist wird, sowie einlösbare Prämien – generisch (nur
  Protokollierung) oder "Internet-Zeit" (schaltet eine hinterlegte
  Entität für konfigurierbare Dauer ein, übersteht HA-Neustarts)
- **Services** für Automationen/Skripte: `add_task`, `update_task`,
  `remove_task`, `assign_task`, `unassign_task`, `complete_task`,
  `approve_task`, `reject_task`, `undo_completion`, `reset_score`,
  `perform_awards`, `reset_wins`, `add_template`, `update_template`,
  `remove_template`, `create_task_from_template`, `add_reward`,
  `update_reward`, `remove_reward`, `request_redemption`,
  `approve_redemption`, `reject_redemption`
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

Nach der Einrichtung erscheinen automatisch ein neuer Eintrag
**"Aufgaben"** in der Seitenleiste sowie die Custom Card (auch sichtbar
unter **Einstellungen → Dashboards → Ressourcen**, sofern deine
Dashboards im Storage-Modus laufen – dem Standard). Für eine
Aufgaben-Übersicht mit allen (nicht nur eigenen) offenen Aufgaben siehe
zusätzlich den Abschnitt "Aufgaben im Dashboard anzeigen" weiter unten.

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

#### Admin per Automation benachrichtigen, wenn eine Freigabe wartet

Für beide Freigabe-Arten (Aufgaben und Prämien-Einlösungen) werden
eigene Events gefeuert, sobald eine Anfrage entsteht:
`aufgaben_scoreboard_task_completion_requested` bzw.
`aufgaben_scoreboard_reward_redemption_requested`. Damit lässt sich
schon heute eine Benachrichtigungs-Automation bauen:

```yaml
alias: Aufgaben-Punktesystem – Freigabe erforderlich
description: Benachrichtigt den Admin, sobald eine Aufgabe oder Prämie auf Freigabe wartet.
triggers:
  - trigger: event
    event_type: aufgaben_scoreboard_task_completion_requested
    id: aufgabe
  - trigger: event
    event_type: aufgaben_scoreboard_reward_redemption_requested
    id: praemie
condition: []
actions:
  - variables:
      benutzer_name: >-
        {% set uid = trigger.event.data.user_id %}
        {% set sensor = states.sensor | selectattr('attributes.user_id', 'defined') | selectattr('attributes.user_id', 'eq', uid) | first %}
        {{ sensor.name if sensor else uid }}
      titel: >-
        {% if trigger.id == 'aufgabe' %}
          Aufgabe wartet auf Freigabe
        {% else %}
          Prämie wartet auf Freigabe
        {% endif %}
      nachricht: >-
        {% if trigger.id == 'aufgabe' %}
          {% set tid = trigger.event.data.task_id %}
          {% set aufgabe = state_attr('sensor.aufgaben_punktesystem_offene_aufgaben_alle_benutzer', 'wartende_aufgaben') | selectattr('id', 'eq', tid) | first %}
          {{ benutzer_name }} hat "{{ aufgabe.name if aufgabe else 'eine Aufgabe' }}" als erledigt gemeldet.
        {% else %}
          {% set rid = trigger.event.data.reward_id %}
          {% set eintrag = state_attr('sensor.aufgaben_punktesystem_offene_aufgaben_alle_benutzer', 'wartende_praemien') | selectattr('reward_id', 'eq', rid) | selectattr('user_id', 'eq', trigger.event.data.user_id) | first %}
          {{ benutzer_name }} möchte "{{ eintrag.reward_name if eintrag else 'eine Prämie' }}" einlösen.
        {% endif %}
  - action: notify.send_message
    target:
      entity_id: notify.dein_handy
    data:
      title: "{{ titel }}"
      message: "{{ nachricht }}"
mode: queued
max: 10
```

`notify.dein_handy` durch die eigene Notify-Entität ersetzen (z. B. die
der Companion App – `notify.send_message` mit Entity-Target ist die
aktuelle Schreibweise, nicht mehr `notify.mobile_app_*` als
Service-Name). Nutzt du kein Prämien-System, lassen sich der zweite
Trigger-Block (`id: praemie`) und der zugehörige `{% else %}`-Zweig
weglassen.

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
- **Automatisch per Entitäts-Trigger**: über eine optionale Entität
  direkt im Formular, mit denselben Bedingungsarten wie beim
  Zustands-Trigger im Automationen-Editor (inkl. derselben Entitäts-/
  Zustands-Auswahl-Komponente):
  - **Von / Zu**: exakter Zustandstext, beide optional. „Zu“ allein
    löst bei jedem Erreichen dieses Zustands aus; zusätzlich „Von“
    schränkt das auf den Übergang aus GENAU diesem Ausgangszustand ein.
  - **Über / Unter**: numerischer Schwellwert, unabhängig von Von/Zu
    nutzbar – auch gleichzeitig, für einen Wertebereich (z. B. „über 10
    und unter 30“).
  
  Sobald die Bedingung erfüllt ist, wird automatisch eine Aufgabe
  angelegt – aber nur, wenn nicht bereits eine offene Aufgabe aus
  derselben Vorlage existiert (Duplikat-Schutz).
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

### Siegerehrung

Der Button „Siegerehrung durchführen" (nur für Administratoren, oberhalb
der Rangliste) ermittelt den/die Benutzer mit dem aktuell höchsten
Punktestand – bei Gleichstand gewinnen **alle** Führenden gleichermaßen,
ein Punktestand von 0 zählt nicht als Sieg. Vor der Bestätigung zeigt
ein Dialog an, wer gerade führt. Nach der Durchführung:

- Der **Sieg-Zähler** der Gewinner erhöht sich dauerhaft um 1 (🏆-Badge
  in der Rangliste) – übersteht auch normale Punktestand-Resets.
- **Alle** Punktestände werden gleichzeitig auf 0 zurückgesetzt, eine
  neue Runde beginnt. Die Erledigungs-Historie bleibt dabei (anders als
  beim einzelnen „Zurücksetzen"-Button) erhalten.
- Ist das Prämien-System aktiviert (siehe unten), wird zusätzlich jedem
  Benutzer sein Punktestand vor dem Reset aufs Punktekonto gutgeschrieben.

Der Sieg-Zähler lässt sich pro Benutzer separat über „Siege
zurücksetzen" auf 0 setzen, unabhängig vom Punktestand.

### Fälligkeit & Erinnerung

Beim Anlegen/Bearbeiten einer Aufgabe (manuell oder als Standardaufgabe)
lassen sich zwei unabhängige, gleichzeitig nutzbare Fristen setzen:

- **Fällig in X Tagen**: taggenau ab heute berechnet. Überfällige
  Aufgaben werden im Panel rot hervorgehoben (Rangliste-Ansicht und
  Verwaltungs-Tab); zusätzlich feuert das Erreichen des Datums einmalig
  das Event `aufgaben_scoreboard_task_overdue`.
- **Erinnerung nach X Tagen offen**: unabhängig von der Fälligkeit,
  löst einmalig `aufgaben_scoreboard_task_reminder` aus, sobald die
  Aufgabe seit dieser Anzahl Tage ununterbrochen offen ist. Beide Fristen
  lassen sich kombinieren, um z. B. zweimal zu erinnern - einmal vorher,
  einmal bei Fälligkeit.

Beide Events eignen sich direkt für eine Benachrichtigungs-Automation,
nach demselben Muster wie bei den Freigabe-Benachrichtigungen weiter
oben:

```yaml
alias: Aufgaben-Punktesystem – Fälligkeit & Erinnerung
description: Benachrichtigt, wenn eine Aufgabe überfällig wird oder seit X Tagen offen ist.
triggers:
  - trigger: event
    event_type: aufgaben_scoreboard_task_overdue
    id: ueberfaellig
  - trigger: event
    event_type: aufgaben_scoreboard_task_reminder
    id: erinnerung
condition: []
actions:
  - variables:
      titel: >-
        {% if trigger.id == 'ueberfaellig' %}
          Aufgabe überfällig
        {% else %}
          Erinnerung: Aufgabe noch offen
        {% endif %}
      nachricht: >-
        {% if trigger.id == 'ueberfaellig' %}
          "{{ trigger.event.data.name }}" ist jetzt überfällig.
        {% else %}
          "{{ trigger.event.data.name }}" ist immer noch offen.
        {% endif %}
  - action: notify.send_message
    target:
      entity_id: notify.dein_handy
    data:
      title: "{{ titel }}"
      message: "{{ nachricht }}"
mode: queued
max: 10
```

`notify.dein_handy` wieder durch die eigene Notify-Entität ersetzen.
Beide Trigger lassen sich auch einzeln nutzen, falls nur eines der
beiden Events interessiert – dann einfach den jeweils anderen
Trigger-Block und den zugehörigen `{% if %}`-Zweig weglassen.

### Punktabzug (manuell, unabhängig von Aufgaben)

Über das ⋮-Menü neben jedem Benutzer in der Rangliste steht zusätzlich
zu den bestehenden Zurücksetzen-Optionen „Punkte abziehen" zur
Verfügung (z. B. für Fehlverhalten, losgelöst vom Aufgabensystem). Der
Punktestand fällt dabei nie unter 0. Ein Abzug erscheint automatisch im
normalen Erledigungs-Verlauf des Benutzers (als negativer Eintrag) und
lässt sich dort über „Rückgängig" innerhalb der üblichen Grenzen (7
Tage / letzte 20 Einträge) wieder aufheben.

### Prämien-System (optional)

Standardmäßig **deaktiviert**. Aktivierbar über **Einstellungen →
Geräte & Dienste → Aufgaben-Punktesystem → Konfigurieren**. Nach
Aktivierung bekommt jeder Benutzer ein **Punktekonto** (💰-Badge in der
Rangliste), das bei jeder Siegerehrung um seinen jeweiligen Punktestand
wächst – ein laufendes Guthaben über beliebig viele Runden hinweg, kein
Rundenlimit. Ein Klick auf den 💰-Badge klappt einen **eigenständigen
Punktekonto-Verlauf** auf (getrennt vom Aufgaben-Verlauf, der über den
Namen aufklappbar ist) – zeigt Zugänge aus Siegerehrungen und Abgänge
aus genehmigten Prämien-Einlösungen chronologisch.

Administratoren legen im Bereich „Prämien verwalten" Prämien mit einem
Punktepreis an:

- **Generisch**: reiner Eintrag, keine automatische Aktion – nur
  Protokollierung + Event (`aufgaben_scoreboard_reward_redemption_*`),
  z. B. für eigene Automationen wie eine Admin-Benachrichtigung.
- **Internet-Zeit**: schaltet eine hinterlegte `switch`-Entität für eine
  konfigurierbare Dauer ein und nach Ablauf automatisch wieder aus –
  übersteht dabei auch einen Home-Assistant-Neustart während der
  laufenden Zeit (die verbleibende Restzeit wird beim Start geprüft und
  ggf. sofort nachgeholt).

Benutzer sehen ihr Guthaben und die verfügbaren Prämien im Bereich „Mein
Punktekonto" und können dort „Einlösen" anfragen – der „Einlösen"-Button
ist deaktiviert, solange das Guthaben nicht ausreicht. Wie bei der
Aufgaben-Erledigung muss ein Administrator die Anfrage erst freigeben
(Bereich „Prämien-Einlösungen zur Freigabe"), bevor die Punkte
abgebucht bzw. eine Internet-Zeit-Entität geschaltet wird.

### Custom Card im Dashboard

Über den Dashboard-Editor eine neue Karte hinzufügen und
`Aufgaben-Scoreboard Karte` auswählen, oder per YAML:

```yaml
type: custom:aufgaben-scoreboard-card
```

Die Karte benötigt keine weitere Konfiguration – sie erkennt den
angemeldeten Benutzer automatisch und zeigt dessen offene Aufgaben samt
"Erledigt"-Button.

**Hinweis zur Registrierung:** Die Karte wird nach dem offiziellen
Community-Leitfaden ["Developer Guide: Embedded Lovelace Card in a Home
Assistant Integration"](https://gist.github.com/KipK/3cf706ac89573432803aaa2f5ca40492)
registriert – über das echte, laufende Lovelace-Objekt von Home
Assistant (`hass.data["lovelace"]`), inklusive Warten auf dessen
vollständiges Laden und versionierten Ressourcen-URLs (`?v=1.4.0`) für
zuverlässiges Cache-Busting nach Updates. Das umgeht gezielt einen
bestätigten Home-Assistant-Core-Bug ([#165767](https://github.com/home-assistant/core/issues/165767)),
bei dem ein roher, separater Zugriff auf die Lovelace-Ressourcen-Storage
(der in früheren Versionen dieser Integration verwendet wurde) mit dem
echten, lazy geladenen Objekt kollidieren und Einträge überschreiben
konnte. Funktioniert automatisch nur im **Storage-Modus** (dem
Standard); im YAML-Modus muss die Ressource manuell eingetragen werden:

```yaml
resources:
  - url: /aufgaben_scoreboard_frontend/aufgaben-scoreboard-card.js
    type: module
```

### Aufgaben im Dashboard anzeigen (Markdown-Karte)

Alternative zur Custom Card oben: Eine Übersicht **aller** offenen
Aufgaben (nicht nur der eigenen) lässt sich auch mit einer **nativen
Markdown-Karte** abbilden - kein Custom Element, keine zusätzliche
JavaScript-Registrierung nötig. Neue Karte → **Markdown** → in den
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
| `aufgaben_scoreboard.deduct_points` | Punkte manuell abziehen, unabhängig von Aufgaben (nie unter 0, per „Rückgängig" umkehrbar) | ✅ |
| `aufgaben_scoreboard.perform_awards` | Siegerehrung durchführen: Sieg-Zähler des/der Gewinner +1, danach alle Punktestände zurücksetzen | ✅ |
| `aufgaben_scoreboard.reset_wins`    | Sieg-Zähler eines Benutzers auf 0 zurücksetzen         | ✅        |
| `aufgaben_scoreboard.add_reward`    | Prämie anlegen (nur bei aktiviertem Prämien-System relevant) | ✅   |
| `aufgaben_scoreboard.update_reward` | Prämie nachträglich bearbeiten                         | ✅        |
| `aufgaben_scoreboard.remove_reward` | Prämie löschen                                         | ✅        |
| `aufgaben_scoreboard.request_redemption` | Prämie anfragen (wartet danach auf Freigabe, noch kein Punktabzug) | Nein¹ |
| `aufgaben_scoreboard.approve_redemption` | Einlösung freigeben, Punkte werden abgebucht (+ ggf. Entität geschaltet) | ✅ |
| `aufgaben_scoreboard.reject_redemption` | Einlösung ablehnen, kein Punktabzug                 | ✅        |
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
