/**
 * Aufgaben-Scoreboard Sidebar-Panel
 * ===================================
 *
 * Dieses Custom Element wird als eigenständige Seite in der
 * Home-Assistant-Seitenleiste registriert (siehe __init__.py,
 * async_register_built_in_panel). Es bietet die VOLLSTÄNDIGE
 * Verwaltung der Integration:
 *
 *   - Übersicht aller Benutzer mit ihrem Punktestand
 *   - Liste aller offenen Aufgaben (mit Zuweisung, Löschen-Button) -
 *     nur für Administratoren sichtbar
 *   - Formular zum Anlegen neuer Aufgaben (inkl. Auswahl, welchen
 *     Benutzern die Aufgabe zugewiesen werden soll) - nur für
 *     Administratoren
 *   - Für jeden Benutzer: seine eigenen offenen Aufgaben mit einem
 *     "Erledigt"-Button (jeder Benutzer darf hier nur seine eigenen
 *     Aufgaben abhaken - serverseitig zusätzlich abgesichert)
 *
 * Auch dieses Element kommt bewusst ohne Build-Schritt / Framework aus
 * und nutzt reines JavaScript mit Shadow DOM sowie die Home-Assistant-
 * eigenen CSS-Variablen für ein zum Theme passendes Erscheinungsbild.
 */

class AufgabenScoreboardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    // Merkt sich, ob das "Neue Aufgabe"-Formular gerade aufgeklappt ist.
    this._formularOffen = false;
    // Merkt sich einen "Fingerabdruck" der zuletzt gerenderten, für uns
    // relevanten Daten. Home Assistant ruft den hass-Setter bei JEDER
    // Zustandsänderung im gesamten System auf (also z. B. auch, wenn
    // irgendein völlig anderer Sensor im Haus seinen Wert ändert). Ohne
    // diesen Vergleich würde das Panel dadurch ständig komplett neu
    // gerendert werden, was mitten in der Eingabe den Fokus aus den
    // Formularfeldern wirft. Wir rendern daher nur dann neu, wenn sich
    // wirklich etwas für uns Relevantes geändert hat.
    this._letzteSignatur = null;
  }

  /**
   * Wird von Home Assistant gesetzt und bei JEDER Zustandsänderung im
   * gesamten System erneut aufgerufen (enthält u. a. alle
   * Entitäts-Zustände). Wir speichern die Referenz immer (wird für
   * Service-Aufrufe benötigt), rendern die Oberfläche aber nur neu,
   * wenn sich die für uns relevanten Daten tatsächlich geändert haben.
   */
  set hass(hass) {
    this._hass = hass;
    const signatur = this._berechneSignatur(hass);
    if (signatur === this._letzteSignatur) {
      return;
    }
    this._letzteSignatur = signatur;
    this._render();
  }

  /**
   * Erstellt eine kompakte Zeichenkette aus allen für dieses Panel
   * relevanten Entitäts-Zuständen (unsere Punkte-Sensoren + die
   * Übersichts-Entität) sowie den Admin-Status des Benutzers. Ändert
   * sich diese Zeichenkette nicht, gibt es für das Panel nichts neu zu
   * zeichnen.
   */
  _berechneSignatur(hass) {
    if (!hass) return "";
    const teile = [];
    for (const entityId in hass.states) {
      if (!entityId.startsWith("sensor.")) continue;
      const zustand = hass.states[entityId];
      const attrs = zustand.attributes || {};
      if (attrs.user_id || Array.isArray(attrs.alle_aufgaben)) {
        teile.push(`${entityId}=${zustand.state}|${JSON.stringify(attrs)}`);
      }
    }
    teile.sort();
    teile.push(`admin=${hass.user ? hass.user.is_admin : ""}`);
    teile.push(`uid=${hass.user ? hass.user.id : ""}`);
    return teile.join("~~");
  }

  /** Wird von Home Assistant beim Anzeigen des Panels gesetzt. */
  set panel(panel) {
    this._panel = panel;
  }

  /** Zeigt an, ob die Seitenleiste im schmalen (mobilen) Modus ist. */
  set narrow(narrow) {
    if (this._narrow === narrow) return;
    this._narrow = narrow;
    this._render();
  }

  // -----------------------------------------------------------------
  // Datenzugriff: Sammelt die relevanten Informationen aus den
  // Zuständen der von der Integration erzeugten Sensor-Entitäten.
  // -----------------------------------------------------------------

  _istAdmin() {
    return !!(this._hass && this._hass.user && this._hass.user.is_admin);
  }

  _sammleBenutzerSensoren() {
    if (!this._hass) return [];
    const states = this._hass.states;
    const ergebnis = [];
    for (const entityId in states) {
      if (!entityId.startsWith("sensor.")) continue;
      const zustand = states[entityId];
      if (zustand.attributes && zustand.attributes.user_id && Array.isArray(zustand.attributes.offene_aufgaben)) {
        ergebnis.push({ entityId, zustand });
      }
    }
    return ergebnis;
  }

  _findeUebersichtsSensor() {
    if (!this._hass) return null;
    const states = this._hass.states;
    for (const entityId in states) {
      if (
        entityId.startsWith("sensor.") &&
        states[entityId].attributes &&
        Array.isArray(states[entityId].attributes.alle_aufgaben)
      ) {
        return states[entityId];
      }
    }
    return null;
  }

  // -----------------------------------------------------------------
  // Service-Aufrufe
  // -----------------------------------------------------------------

  _aufgabeErledigen(taskId, userId) {
    this._hass.callService("aufgaben_scoreboard", "complete_task", {
      task_id: taskId,
      user_id: userId,
    });
  }

  _aufgabeLoeschen(taskId) {
    this._hass.callService("aufgaben_scoreboard", "remove_task", {
      task_id: taskId,
    });
  }

  _aufgabeZuweisen(taskId, userId) {
    if (!userId) return;
    this._hass.callService("aufgaben_scoreboard", "assign_task", {
      task_id: taskId,
      user_id: userId,
    });
  }

  _neueAufgabeAnlegen(formData) {
    this._hass.callService("aufgaben_scoreboard", "add_task", formData);
  }

  // -----------------------------------------------------------------
  // Rendering
  // -----------------------------------------------------------------

  /**
   * Sichert die aktuell im "Neue Aufgabe"-Formular eingegebenen Werte
   * sowie das Feld, das gerade den Fokus hat (inkl. Cursor-Position).
   * Wird direkt vor dem Neuzeichnen der Oberfläche aufgerufen, damit ein
   * währenddessen unvermeidbares Re-Render (z. B. weil sich currently
   * wirklich Daten geändert haben) die Benutzereingabe nicht verwirft.
   */
  _sichereFormularZustand() {
    const formular = this.shadowRoot.getElementById("neue-aufgabe-formular");
    if (!formular) return null;

    const aktivesElement = this.shadowRoot.activeElement;
    const werte = {};
    formular.querySelectorAll("input, textarea, select").forEach((feld) => {
      if (!feld.name) return;
      werte[feld.name] = feld.multiple
        ? Array.from(feld.selectedOptions).map((o) => o.value)
        : feld.value;
    });

    return {
      werte,
      fokusName: aktivesElement && aktivesElement.name ? aktivesElement.name : null,
      selectionStart:
        aktivesElement && "selectionStart" in aktivesElement ? aktivesElement.selectionStart : null,
      selectionEnd: aktivesElement && "selectionEnd" in aktivesElement ? aktivesElement.selectionEnd : null,
    };
  }

  /** Stellt die mit _sichereFormularZustand() gesicherten Werte/Fokus wieder her. */
  _stelleFormularZustandWieder(zustand) {
    if (!zustand) return;
    const formular = this.shadowRoot.getElementById("neue-aufgabe-formular");
    if (!formular) return;

    formular.querySelectorAll("input, textarea, select").forEach((feld) => {
      if (!feld.name || !(feld.name in zustand.werte)) return;
      const wert = zustand.werte[feld.name];
      if (feld.multiple) {
        Array.from(feld.options).forEach((option) => {
          option.selected = wert.includes(option.value);
        });
      } else {
        feld.value = wert;
      }
    });

    if (zustand.fokusName) {
      const feld = formular.querySelector(`[name="${zustand.fokusName}"]`);
      if (feld) {
        feld.focus();
        if (zustand.selectionStart != null && "setSelectionRange" in feld) {
          try {
            feld.setSelectionRange(zustand.selectionStart, zustand.selectionEnd);
          } catch (fehler) {
            // Manche Feldtypen (z. B. number) unterstützen setSelectionRange
            // nicht - das ist unkritisch, der Wert selbst bleibt erhalten.
          }
        }
      }
    }
  }

  _render() {
    if (!this._hass) return;

    // Formularzustand sichern, BEVOR das DOM ersetzt wird.
    const gesicherterFormularZustand = this._sichereFormularZustand();

    const istAdmin = this._istAdmin();
    const benutzerSensoren = this._sammleBenutzerSensoren();
    const uebersichtsSensor = this._findeUebersichtsSensor();
    const eigeneUserId = this._hass.user ? this._hass.user.id : null;

    this.shadowRoot.innerHTML = `
      <style>${this._css()}</style>
      <div class="wrapper">
        <div class="kopf">
          <h1>🏆 Aufgaben-Punktesystem</h1>
        </div>

        <div class="rangliste">
          ${benutzerSensoren
            .slice()
            .sort((a, b) => Number(b.zustand.state) - Number(a.zustand.state))
            .map(
              (b) => `
              <div class="rang-eintrag ${b.zustand.attributes.user_id === eigeneUserId ? "ich" : ""}">
                <span class="rang-name">${this._escape(b.zustand.attributes.friendly_name || b.entityId)}</span>
                <span class="rang-punkte">${b.zustand.state} Pkt.</span>
              </div>`
            )
            .join("")}
        </div>

        <div class="abschnitt">
          <h2>Meine offenen Aufgaben</h2>
          ${this._renderEigeneAufgaben(benutzerSensoren, eigeneUserId)}
        </div>

        ${istAdmin ? this._renderAdminBereich(uebersichtsSensor, benutzerSensoren) : ""}
      </div>
    `;

    this._eventListenerRegistrieren(istAdmin, benutzerSensoren);

    // Gesicherte Formularwerte + Fokus wiederherstellen (falls das
    // Formular offen war und Re-Render trotzdem stattgefunden hat).
    this._stelleFormularZustandWieder(gesicherterFormularZustand);
  }

  _renderEigeneAufgaben(benutzerSensoren, eigeneUserId) {
    const eigener = benutzerSensoren.find((b) => b.zustand.attributes.user_id === eigeneUserId);
    const aufgaben = eigener ? eigener.zustand.attributes.offene_aufgaben : [];

    if (!aufgaben || aufgaben.length === 0) {
      return `<div class="hinweis">Keine offenen Aufgaben für dich. 🎉</div>`;
    }

    return `
      <div class="aufgaben-liste">
        ${aufgaben
          .map(
            (a) => `
          <div class="aufgaben-karte">
            <div class="aufgaben-info">
              <div class="aufgaben-name">${this._escape(a.name)}</div>
              ${a.description ? `<div class="aufgaben-beschreibung">${this._escape(a.description)}</div>` : ""}
            </div>
            <div class="aufgaben-aktion">
              <span class="punkte-badge">+${a.score}</span>
              <button class="btn-primary eigene-erledigen" data-task-id="${a.id}">Erledigt</button>
            </div>
          </div>`
          )
          .join("")}
      </div>
    `;
  }

  _renderAdminBereich(uebersichtsSensor, benutzerSensoren) {
    const alleAufgaben = uebersichtsSensor ? uebersichtsSensor.attributes.alle_aufgaben : [];
    const offeneAufgaben = alleAufgaben.filter((a) => a.status === "open");

    const benutzerOptionen = benutzerSensoren
      .map(
        (b) =>
          `<option value="${b.zustand.attributes.user_id}">${this._escape(
            b.zustand.attributes.friendly_name || b.entityId
          )}</option>`
      )
      .join("");

    return `
      <div class="abschnitt admin-bereich">
        <div class="admin-kopf">
          <h2>Verwaltung (alle Aufgaben)</h2>
          <button class="btn-secondary" id="toggle-formular">
            ${this._formularOffen ? "Formular schließen" : "+ Neue Aufgabe"}
          </button>
        </div>

        ${
          this._formularOffen
            ? `
          <form class="neue-aufgabe-formular" id="neue-aufgabe-formular">
            <label>
              Titel
              <input type="text" name="name" required placeholder="z. B. Rasen mähen" />
            </label>
            <label>
              Beschreibung (optional)
              <textarea name="description" placeholder="Details zur Aufgabe"></textarea>
            </label>
            <label>
              Punkte
              <input type="number" name="score" min="0" value="10" required />
            </label>
            <label>
              Zuweisen an (Mehrfachauswahl möglich, leer = für alle offen)
              <select name="assigned_to" multiple size="4">
                ${benutzerOptionen}
              </select>
            </label>
            <button type="submit" class="btn-primary">Aufgabe anlegen</button>
          </form>
        `
            : ""
        }

        <div class="aufgaben-liste">
          ${
            offeneAufgaben.length === 0
              ? `<div class="hinweis">Aktuell keine offenen Aufgaben.</div>`
              : offeneAufgaben
                  .map(
                    (a) => `
              <div class="aufgaben-karte">
                <div class="aufgaben-info">
                  <div class="aufgaben-name">${this._escape(a.name)}</div>
                  ${a.description ? `<div class="aufgaben-beschreibung">${this._escape(a.description)}</div>` : ""}
                  <div class="aufgaben-zuweisung">
                    Zugewiesen an: ${
                      a.assigned_to && a.assigned_to.length
                        ? a.assigned_to.map((uid) => this._nameFuerUserId(uid, benutzerSensoren)).join(", ")
                        : "Alle Benutzer"
                    }
                  </div>
                </div>
                <div class="aufgaben-aktion">
                  <span class="punkte-badge">+${a.score}</span>
                  <select class="zuweisen-select" data-task-id="${a.id}">
                    <option value="">Zuweisen an...</option>
                    ${benutzerOptionen}
                  </select>
                  <button class="btn-danger loeschen-btn" data-task-id="${a.id}">Löschen</button>
                </div>
              </div>`
                  )
                  .join("")
          }
        </div>
      </div>
    `;
  }

  _nameFuerUserId(userId, benutzerSensoren) {
    const treffer = benutzerSensoren.find((b) => b.zustand.attributes.user_id === userId);
    return treffer ? this._escape(treffer.zustand.attributes.friendly_name || userId) : userId;
  }

  _eventListenerRegistrieren(istAdmin, benutzerSensoren) {
    const eigeneUserId = this._hass.user ? this._hass.user.id : null;

    this.shadowRoot.querySelectorAll(".eigene-erledigen").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        this._aufgabeErledigen(ev.target.getAttribute("data-task-id"), eigeneUserId);
      });
    });

    if (!istAdmin) return;

    const toggleBtn = this.shadowRoot.getElementById("toggle-formular");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        this._formularOffen = !this._formularOffen;
        this._render();
      });
    }

    const formular = this.shadowRoot.getElementById("neue-aufgabe-formular");
    if (formular) {
      formular.addEventListener("submit", (ev) => {
        ev.preventDefault();
        const daten = new FormData(formular);
        const ausgewaehlteBenutzer = Array.from(formular.querySelector("select[name=assigned_to]").selectedOptions).map(
          (o) => o.value
        );
        this._neueAufgabeAnlegen({
          name: daten.get("name"),
          description: daten.get("description") || "",
          score: Number(daten.get("score")),
          assigned_to: ausgewaehlteBenutzer,
        });
        this._formularOffen = false;
        this._render();
      });
    }

    this.shadowRoot.querySelectorAll(".loeschen-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        if (confirm("Diese Aufgabe wirklich löschen?")) {
          this._aufgabeLoeschen(ev.target.getAttribute("data-task-id"));
        }
      });
    });

    this.shadowRoot.querySelectorAll(".zuweisen-select").forEach((select) => {
      select.addEventListener("change", (ev) => {
        this._aufgabeZuweisen(ev.target.getAttribute("data-task-id"), ev.target.value);
        ev.target.value = "";
      });
    });
  }

  _escape(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : text;
    return div.innerHTML;
  }

  _css() {
    return `
      :host {
        display: block;
        background: var(--primary-background-color);
        min-height: 100vh;
        box-sizing: border-box;
      }
      .wrapper {
        max-width: 800px;
        margin: 0 auto;
        padding: 24px 16px 64px 16px;
      }
      .kopf h1 {
        font-size: 1.6em;
        color: var(--primary-text-color);
        margin: 0 0 20px 0;
      }
      h2 {
        font-size: 1.15em;
        color: var(--primary-text-color);
        margin: 0 0 12px 0;
      }
      .abschnitt {
        margin-top: 32px;
      }
      .rangliste {
        background: var(--card-background-color);
        border-radius: 12px;
        box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,0.12));
        overflow: hidden;
      }
      .rang-eintrag {
        display: flex;
        justify-content: space-between;
        padding: 12px 16px;
        border-bottom: 1px solid var(--divider-color, #eee);
        color: var(--primary-text-color);
      }
      .rang-eintrag:last-child { border-bottom: none; }
      .rang-eintrag.ich { background: rgba(var(--rgb-primary-color, 3,169,244), 0.08); font-weight: 600; }
      .rang-punkte { color: var(--primary-color); font-weight: 700; }

      .hinweis {
        color: var(--secondary-text-color);
        padding: 12px 4px;
      }

      .aufgaben-liste {
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .aufgaben-karte {
        background: var(--card-background-color);
        border-radius: 12px;
        box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,0.12));
        padding: 14px 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
      }
      .aufgaben-name {
        font-weight: 600;
        color: var(--primary-text-color);
      }
      .aufgaben-beschreibung {
        color: var(--secondary-text-color);
        font-size: 0.9em;
        margin-top: 2px;
      }
      .aufgaben-zuweisung {
        color: var(--secondary-text-color);
        font-size: 0.8em;
        margin-top: 6px;
      }
      .aufgaben-aktion {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }
      .punkte-badge {
        background: var(--primary-color);
        color: var(--text-primary-color, #fff);
        border-radius: 999px;
        padding: 3px 10px;
        font-weight: 700;
        font-size: 0.85em;
      }
      .btn-primary, .btn-secondary, .btn-danger {
        border: none;
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 0.9em;
        cursor: pointer;
      }
      .btn-primary {
        background: var(--primary-color);
        color: var(--text-primary-color, #fff);
      }
      .btn-secondary {
        background: transparent;
        color: var(--primary-color);
        border: 1px solid var(--primary-color);
      }
      .btn-danger {
        background: var(--error-color, #db4437);
        color: #fff;
      }
      .admin-kopf {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
      }
      .neue-aufgabe-formular {
        display: flex;
        flex-direction: column;
        gap: 12px;
        background: var(--card-background-color);
        border-radius: 12px;
        padding: 16px;
        margin: 16px 0;
        box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,0.12));
      }
      .neue-aufgabe-formular label {
        display: flex;
        flex-direction: column;
        gap: 4px;
        font-size: 0.9em;
        color: var(--secondary-text-color);
      }
      .neue-aufgabe-formular input,
      .neue-aufgabe-formular textarea,
      .neue-aufgabe-formular select {
        font-family: inherit;
        font-size: 1em;
        padding: 8px;
        border-radius: 6px;
        border: 1px solid var(--divider-color, #ccc);
        background: var(--primary-background-color);
        color: var(--primary-text-color);
      }
      .zuweisen-select {
        max-width: 140px;
      }
    `;
  }
}

customElements.define("aufgaben-scoreboard-panel", AufgabenScoreboardPanel);
