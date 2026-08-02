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
 */

class AufgabenScoreboardCard extends HTMLElement {
  /**
   * Wird von Home Assistant aufgerufen, sobald sich der globale
   * Zustand (hass-Objekt) ändert - also im Prinzip bei jeder
   * Zustandsänderung im System. Wir rendern hier neu, sofern sich
   * unsere relevante Sensor-Entität tatsächlich geändert hat.
   */
  set hass(hass) {
    this._hass = hass;
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
      if (
        zustand.attributes &&
        zustand.attributes.user_id === eigeneUserId &&
        Array.isArray(zustand.attributes.offene_aufgaben)
      ) {
        return zustand;
      }
    }
    return null;
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
    const offeneAufgaben = sensor.attributes.offene_aufgaben || [];

    const aufgabenHtml = offeneAufgaben.length
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

customElements.define("aufgaben-scoreboard-card", AufgabenScoreboardCard);

// Registriert die Karte im grafischen Karten-Auswahldialog von Lovelace,
// damit sie dort mit Namen/Beschreibung/Icon auffindbar ist.
window.customCards = window.customCards || [];
window.customCards.push({
  type: "aufgaben-scoreboard-card",
  name: "Aufgaben-Scoreboard Karte",
  description: "Zeigt deine offenen Aufgaben und deinen Punktestand.",
  preview: false,
});
