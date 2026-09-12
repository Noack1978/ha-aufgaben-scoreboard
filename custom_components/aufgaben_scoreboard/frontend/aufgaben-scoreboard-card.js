/**
 * Aufgaben-Scoreboard Custom Card
 * =================================
 *
 * Diese Datei definiert das Custom Element "aufgaben-scoreboard-card",
 * das in jedem Lovelace-Dashboard über
 *
 *     type: custom:aufgaben-scoreboard-card
 *
 * eingebunden werden kann. Die Karte ist bewusst schlank gehalten und
 * für die "normale" Benutzeransicht gedacht: Sie zeigt
 *
 *   - den aktuellen Punktestand des eingeloggten Benutzers,
 *   - seine offenen Aufgaben (zugewiesen ODER für alle offen),
 *   - einen Button, um eine Aufgabe direkt als erledigt zu markieren.
 *
 * Für die vollständige Verwaltung (Aufgaben anlegen, zuweisen, löschen,
 * alle Benutzer im Überblick) gibt es das separate Sidebar-Panel
 * (aufgaben-scoreboard-panel.js), das automatisch in der Seitenleiste
 * erscheint.
 *
 * Es wird bewusst KEIN Build-Schritt / Framework (z. B. LitElement)
 * vorausgesetzt, damit die Karte ohne zusätzliche Abhängigkeiten direkt
 * vom Home-Assistant-Server ausgeliefert werden kann. Home Assistants
 * eigene CSS-Variablen (z. B. --primary-color) werden verwendet, damit
 * sich die Karte automatisch an das aktive Theme (hell/dunkel) anpasst.
 *
 * WICHTIG - Architekturhinweis (seit Version 2.0.0 des Panels, hier
 * nachgezogen): Die offenen Aufgaben stehen NICHT mehr als
 * Sensor-Attribut zur Verfügung, sondern werden als JSON-Datei unter
 * config/www/aufgaben_scoreboard/daten.json bereitgestellt (Home
 * Assistant liefert den Inhalt von config/www/ automatisch unter
 * /local/ aus). Der Hintergrund: Diese Liste wuchs mit der Zeit über
 * Home Assistants Grenze von 16 KB pro Zustandsattribut hinaus. Die
 * Karte lädt die Datei per fetch() und tut das erneut, sobald sich der
 * "Offene Aufgaben"-Zähler-Sensor ändert (siehe sensor.py,
 * AlleOffenenAufgabenSensor) - dieser dient nur noch als
 * leichtgewichtiges Änderungssignal, nicht mehr als Datenquelle selbst.
 */

class AufgabenScoreboardCard extends HTMLElement {
  constructor() {
    super();
    // Zwischengespeicherte "große" Panel-Daten - siehe Datei-Docstring
    // oben. Mit einer sinnvollen Leervorbelegung, damit _render() auch
    // vor dem ersten erfolgreichen Abruf funktioniert.
    this._panelDaten = { offene_aufgaben: [] };
    // Merkt sich einen "Fingerabdruck" NUR des "Offene Aufgaben"-
    // Zähler-Sensors - ändert sich dieser, müssen die Panel-Daten per
    // fetch() neu geladen werden. null markiert "noch nie geladen" und
    // erzwingt damit den allerersten Abruf.
    this._letzteZaehlerSignatur = null;
    // Fortlaufender Zähler zum Schutz vor einer Race Condition, falls
    // mehrere fetch()-Anfragen kurz hintereinander laufen und in der
    // falschen Reihenfolge zurückkommen - siehe _aktualisierePanelDaten().
    this._panelDatenAnfrageZaehler = 0;
  }

  /**
   * Wird von Home Assistant aufgerufen, sobald sich der globale
   * Zustand (hass-Objekt) ändert - also im Prinzip bei JEDER
   * Zustandsänderung im gesamten System, auch bei völlig fachfremden
   * Entitäten. Um unnötige (und potenziell störende) Neuzeichnungen zu
   * vermeiden, wird nur dann neu gerendert, wenn sich die für diese
   * Karte relevante Sensor-Entität tatsächlich geändert hat.
   *
   * Zusätzlich: Ändert sich speziell der "Offene Aufgaben"-Zähler-
   * Sensor, werden die Panel-Daten per fetch() neu geladen (siehe
   * Datei-Docstring).
   */
  set hass(hass) {
    this._hass = hass;

    const zaehlerSignatur = this._berechneZaehlerSignatur();
    if (zaehlerSignatur !== this._letzteZaehlerSignatur) {
      this._letzteZaehlerSignatur = zaehlerSignatur;
      // Bewusst nicht auf das Ergebnis warten - der fetch()-Aufruf
      // rendert am Ende selbst neu (siehe _aktualisierePanelDaten()).
      this._aktualisierePanelDaten();
    }

    const sensor = this._findeEigenenSensor();
    const signatur = sensor ? `${sensor.state}|${JSON.stringify(sensor.attributes)}` : "";
    if (signatur === this._letzteSignatur) {
      return;
    }
    this._letzteSignatur = signatur;
    this._render();
  }

  /**
   * Wird von Home Assistant beim Hinzufügen der Karte zu einem
   * Dashboard aufgerufen. Für diese Karte wird keine Konfiguration
   * benötigt, daher bleibt die Methode leer.
   */
  setConfig(config) {
    this._config = config || {};
  }

  /**
   * Hilft dem Lovelace-Karten-Editor, eine sinnvolle Standardgröße
   * für die Karte in "Masonry"-Ansichten zu wählen.
   */
  getCardSize() {
    return 3;
  }

  /**
   * Liefert eine minimale Standard-Konfiguration, wenn ein Benutzer die
   * Karte über den grafischen Karten-Editor hinzufügt.
   */
  static getStubConfig() {
    return {};
  }

  /**
   * Ermittelt die Sensor-Entität mit dem Punktestand des aktuell
   * eingeloggten Benutzers, indem alle Entitäten der Integration nach
   * der passenden user_id im Attribut durchsucht werden.
   *
   * WICHTIG: Prüft bewusst NUR noch "user_id" - das früher zusätzlich
   * geprüfte Attribut "offene_aufgaben" existiert am Benutzer-Sensor
   * seit einer Überarbeitung der Datenspeicherung nicht mehr (siehe
   * Datei-Docstring). Ohne diese Korrektur hätte die Karte NIE mehr
   * einen Sensor gefunden und dauerhaft nur noch die
   * "Kein Punktestand gefunden"-Fehlermeldung gezeigt.
   */
  _findeEigenenSensor() {
    if (!this._hass || !this._hass.user) {
      return null;
    }
    const eigeneUserId = this._hass.user.id;
    const states = this._hass.states;
    for (const entityId in states) {
      if (!entityId.startsWith("sensor.")) continue;
      const zustand = states[entityId];
      if (zustand.attributes && zustand.attributes.user_id === eigeneUserId) {
        return zustand;
      }
    }
    return null;
  }

  /**
   * Prüft, ob der aktuelle Benutzer über den Options-Flow
   * ("Berücksichtigte Benutzer konfigurieren") zugelassen ist - liest
   * dafür das "aufgaben_scoreboard_erlaubte_benutzer"-Attribut vom
   * "Offene Aufgaben"-Zähler-Sensor (siehe sensor.py,
   * AlleOffenenAufgabenSensor). null (Liste nie konfiguriert) bedeutet
   * "alle Benutzer zugelassen". Analog zur selben Prüfung im
   * Sidebar-Panel - ein aus der Auswahl entfernter Benutzer soll auch
   * über diese Karte keine Aufgaben mehr erledigen können.
   */
  _istBenutzerZugelassen() {
    if (!this._hass || !this._hass.user) return true;
    const eigeneUserId = this._hass.user.id;
    const states = this._hass.states;
    for (const entityId in states) {
      if (
        entityId.startsWith("sensor.") &&
        states[entityId].attributes &&
        states[entityId].attributes.aufgaben_scoreboard_sensor_kind === "offene_aufgaben"
      ) {
        const erlaubte = states[entityId].attributes.aufgaben_scoreboard_erlaubte_benutzer;
        return erlaubte === null || erlaubte === undefined || erlaubte.includes(eigeneUserId);
      }
    }
    return true;
  }

  /**
   * Berechnet einen Fingerabdruck NUR aus dem "Offene Aufgaben"-
   * Zähler-Sensor (Zustand + Attribute, inkl. dessen live berechnetem
   * Zeitstempel-Attribut) - entscheidet, wann die Panel-Daten per
   * fetch() neu geladen werden müssen. Der Zeitstempel ändert sich bei
   * WIRKLICH jeder Datenänderung im Manager, nicht nur bei einer
   * geänderten Anzahl offener Aufgaben (siehe sensor.py,
   * _ZaehlerSensor).
   */
  _berechneZaehlerSignatur() {
    if (!this._hass) return "";
    const states = this._hass.states;
    for (const entityId in states) {
      if (
        entityId.startsWith("sensor.") &&
        states[entityId].attributes &&
        states[entityId].attributes.aufgaben_scoreboard_sensor_kind === "offene_aufgaben"
      ) {
        return `${entityId}=${states[entityId].state}|${JSON.stringify(states[entityId].attributes)}`;
      }
    }
    return "";
  }

  /**
   * Lädt die "großen" Panel-Daten per fetch() aus
   * config/www/aufgaben_scoreboard/daten.json und rendert anschließend
   * neu. Siehe Datei-Docstring sowie aufgaben-scoreboard-panel.js
   * (_aktualisierePanelDaten()) für den ausführlichen Hintergrund zu:
   *   - "cache: no-store" (Browser-Cache umgehen)
   *   - zusätzlicher Zeitstempel-Query-Parameter (umgeht zusätzlich
   *     einen von der Companion-App registrierten Service Worker, der
   *     "cache: no-store" ignorieren kann)
   *   - Anfrage-Zähler-Schutz gegen eine Race Condition bei mehreren,
   *     schnell aufeinanderfolgenden Aufrufen
   */
  async _aktualisierePanelDaten() {
    const eigeneAnfrageId = ++this._panelDatenAnfrageZaehler;
    let neueDaten = null;
    try {
      const antwort = await fetch(`/local/aufgaben_scoreboard/daten.json?t=${Date.now()}`, {
        cache: "no-store",
      });
      if (!antwort.ok) {
        throw new Error(`HTTP ${antwort.status}`);
      }
      neueDaten = await antwort.json();
    } catch (fehler) {
      console.error("Aufgaben-Scoreboard-Karte: Panel-Daten konnten nicht geladen werden.", fehler);
    }

    if (eigeneAnfrageId !== this._panelDatenAnfrageZaehler) {
      // Inzwischen wurde eine neuere Anfrage gestartet - dieses jetzt
      // veraltete Ergebnis wird bewusst verworfen.
      return;
    }

    if (neueDaten !== null) {
      this._panelDaten = neueDaten;
    }
    this._render();
  }

  /**
   * Ruft den Service auf, um eine Aufgabe als erledigt zu markieren.
   */
  _aufgabeErledigen(taskId) {
    this._hass.callService("aufgaben_scoreboard", "complete_task", {
      task_id: taskId,
    });
  }

  _render() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }

    const sensor = this._findeEigenenSensor();

    if (!sensor) {
      this.shadowRoot.innerHTML = `
        <ha-card header="Meine Aufgaben">
          <div class="card-content">
            Kein Punktestand für diesen Benutzer gefunden. Ist die
            Integration "Aufgaben-Punktesystem" eingerichtet?
          </div>
        </ha-card>
      `;
      return;
    }

    const punkte = sensor.state;
    const eigeneUserId = sensor.attributes.user_id;
    const istZugelassen = this._istBenutzerZugelassen();

    // Offene Aufgaben werden NICHT mehr pro Benutzer dupliziert
    // gespeichert, sondern hier aus der globalen Liste in den
    // Panel-Daten client-seitig gefiltert - exakt dieselbe Regel wie
    // AufgabenScoreboardManager.get_open_tasks_for_user() im Backend:
    // eine Aufgabe ist "offen für mich", wenn sie niemandem explizit
    // zugewiesen ist (für alle offen) ODER mir explizit zugewiesen ist.
    const alleOffenen = this._panelDaten.offene_aufgaben || [];
    const offeneAufgaben = alleOffenen.filter(
      (a) => !a.assigned_to || a.assigned_to.length === 0 || a.assigned_to.includes(eigeneUserId)
    );

    const nichtZugelassenHinweis = !istZugelassen
      ? `<div class="hinweis-warnung">
          ⚠️ Du bist aktuell nicht (mehr) in der Benutzerauswahl dieser Integration enthalten
          und kannst deshalb keine Aufgaben erledigen.
        </div>`
      : "";

    const aufgabenHtml = !istZugelassen
      ? ""
      : offeneAufgaben.length
      ? offeneAufgaben
          .map(
            (aufgabe) => `
        <div class="aufgabe">
          <div class="aufgabe-info">
            <div class="aufgabe-name">${this._escape(aufgabe.name)}</div>
            ${
              aufgabe.description
                ? `<div class="aufgabe-beschreibung">${this._escape(aufgabe.description)}</div>`
                : ""
            }
          </div>
          <div class="aufgabe-aktion">
            <span class="aufgabe-punkte">+${aufgabe.score}</span>
            <button data-task-id="${aufgabe.id}" class="erledigen-btn">Erledigt</button>
          </div>
        </div>
      `
          )
          .join("")
      : `<div class="keine-aufgaben">Aktuell keine offenen Aufgaben. 🎉</div>`;

    this.shadowRoot.innerHTML = `
      <style>
        ha-card {
          padding: 0;
        }
        .kopfzeile {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
        }
        .titel {
          font-size: 1.1em;
          font-weight: 500;
          color: var(--primary-text-color);
        }
        .punktestand {
          font-size: 1.4em;
          font-weight: 700;
          color: var(--primary-color);
        }
        .card-content {
          padding: 16px;
          color: var(--secondary-text-color);
        }
        .hinweis-warnung {
          margin: 12px 16px;
          padding: 10px 12px;
          color: var(--error-color, #f44336);
          background: rgba(var(--rgb-error-color, 244,67,54), 0.08);
          border: 1px solid var(--error-color, #f44336);
          border-radius: 8px;
          font-size: 0.9em;
        }
        .aufgabe {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 10px 16px;
          border-bottom: 1px solid var(--divider-color, #eeeeee);
        }
        .aufgabe:last-child {
          border-bottom: none;
        }
        .aufgabe-name {
          font-weight: 500;
          color: var(--primary-text-color);
        }
        .aufgabe-beschreibung {
          font-size: 0.85em;
          color: var(--secondary-text-color);
          margin-top: 2px;
        }
        .aufgabe-aktion {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-shrink: 0;
        }
        .aufgabe-punkte {
          font-weight: 600;
          color: var(--primary-color);
        }
        .erledigen-btn {
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          border: none;
          border-radius: 8px;
          padding: 6px 12px;
          font-size: 0.85em;
          cursor: pointer;
        }
        .erledigen-btn:hover {
          opacity: 0.85;
        }
        .keine-aufgaben {
          padding: 16px;
          text-align: center;
          color: var(--secondary-text-color);
        }
      </style>
      <ha-card>
        <div class="kopfzeile">
          <span class="titel">Meine Aufgaben</span>
          <span class="punktestand">${punkte} Pkt.</span>
        </div>
        ${nichtZugelassenHinweis}
        ${aufgabenHtml}
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll(".erledigen-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        this._aufgabeErledigen(ev.target.getAttribute("data-task-id"));
      });
    });
  }

  /** Einfache Absicherung gegen HTML-Injektion in Aufgabennamen/-beschreibungen. */
  _escape(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
}

// Defensiv gegen doppelte Registrierung abgesichert (z. B. falls das
// Modul aus irgendeinem Grund zweimal geladen wird) - ein zweiter
// customElements.define()-Aufruf für denselben Namen würde sonst mit
// einer nicht abgefangenen DOMException abbrechen, noch bevor die
// letzte Zeile dieser Datei (window.customCards.push) erreicht wird.
if (!customElements.get("aufgaben-scoreboard-card")) {
  customElements.define("aufgaben-scoreboard-card", AufgabenScoreboardCard);
}

// Registriert die Karte im grafischen Karten-Auswahldialog von Lovelace,
// damit sie dort mit Namen/Beschreibung/Icon auffindbar ist.
window.customCards = window.customCards || [];
if (!window.customCards.some((karte) => karte.type === "aufgaben-scoreboard-card")) {
  window.customCards.push({
    type: "aufgaben-scoreboard-card",
    name: "Aufgaben-Scoreboard Karte",
    description: "Zeigt deine offenen Aufgaben und deinen Punktestand.",
    preview: false,
  });
}
