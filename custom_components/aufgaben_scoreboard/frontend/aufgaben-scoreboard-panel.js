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
    // Merkt sich, ob das Aufgaben-Formular gerade aufgeklappt ist.
    this._formularOffen = false;
    // Ist dieser Wert gesetzt, befindet sich das Formular im
    // Bearbeitungs-Modus für die Aufgabe mit dieser ID (statt eine neue
    // Aufgabe anzulegen). Wird über den "Bearbeiten"-Button einer
    // Aufgabe gesetzt.
    this._bearbeiteTaskId = null;
    // Analog zu _formularOffen/_bearbeiteTaskId, aber für das
    // Standardaufgaben-Formular. Aufgaben- und Vorlagen-Formular
    // schließen sich gegenseitig aus (siehe _eventListenerRegistrieren) -
    // es gibt daher zu jedem Zeitpunkt höchstens EIN offenes Formular im
    // DOM, was die Formular-Zustand-Sicherung (siehe unten) vereinfacht.
    this._vorlagenFormularOffen = false;
    this._bearbeiteVorlageId = null;
    // Merkt sich, für welchen Benutzer (falls überhaupt) der
    // Erledigungs-Verlauf in der Rangliste gerade aufgeklappt ist -
    // null = keiner. Immer nur einer gleichzeitig aufgeklappt.
    this._aufgeklappterVerlaufUserId = null;
    // Analog, aber für den EIGENSTÄNDIGEN Punktekonto-Verlauf (Zugänge/
    // Abgänge) - bewusst getrennt vom Aufgaben-Verlauf oben, damit
    // beide unabhängig voneinander auf-/zugeklappt werden können.
    this._aufgeklappterPunktekontoUserId = null;
    // Analog zum Vorlagen-Formular, aber für die Prämien-Verwaltung.
    this._praemienFormularOffen = false;
    this._bearbeitePraemieId = null;
    // Aktiver Tab der Panel-Navigation. "benutzer" ist für ALLE
    // Benutzer sichtbar, die übrigen Tabs nur für Administratoren
    // (siehe _render() - fällt automatisch auf "benutzer" zurück,
    // falls der aktive Tab für die aktuellen Rechte nicht existiert).
    this._aktiverTab = "benutzer";
    // Merkt sich, für welchen Benutzer (falls überhaupt) das ⋮-Aktions-
    // Menü in der Rangliste gerade offen ist (Zurücksetzen-Buttons) -
    // null = keins offen. Immer nur eins gleichzeitig, hält die Zeilen
    // im Normalfall kompakt.
    this._offenesRangMenuUserId = null;
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
    // Nur im Panel-Modus (eigene Seite in der Seitenleiste) gesetzt -
    // steuert, ob der Menü-Button (☰) im Header angezeigt wird, über
    // den sich die Seitenleiste ein-/ausblenden lässt (dieselbe Technik
    // wie bei ha-step-challenge, Music Assistant, Beatify).
    this._isPanel = true;
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

  _aufgabeFreigeben(taskId) {
    this._hass.callService("aufgaben_scoreboard", "approve_task", { task_id: taskId });
  }

  _aufgabeAblehnen(taskId) {
    this._hass.callService("aufgaben_scoreboard", "reject_task", { task_id: taskId });
  }

  _erledigungRueckgaengig(completionId) {
    this._hass.callService("aufgaben_scoreboard", "undo_completion", { completion_id: completionId });
  }

  _siegerehrungDurchfuehren() {
    this._hass.callService("aufgaben_scoreboard", "perform_awards", {});
  }

  _siegeZuruecksetzen(userId) {
    this._hass.callService("aufgaben_scoreboard", "reset_wins", { user_id: userId });
  }

  _punkteAbziehen(userId, amount, reason) {
    this._hass.callService("aufgaben_scoreboard", "deduct_points", {
      user_id: userId,
      amount: amount,
      reason: reason,
    });
  }

  _praemieAnlegen(formData) {
    this._hass.callService("aufgaben_scoreboard", "add_reward", formData);
  }

  _praemieAktualisieren(rewardId, formData) {
    this._hass.callService("aufgaben_scoreboard", "update_reward", {
      reward_id: rewardId,
      ...formData,
    });
  }

  _praemieLoeschen(rewardId) {
    this._hass.callService("aufgaben_scoreboard", "remove_reward", { reward_id: rewardId });
  }

  _praemieAnfragen(rewardId, userId) {
    this._hass.callService("aufgaben_scoreboard", "request_redemption", {
      reward_id: rewardId,
      user_id: userId,
    });
  }

  _einloesungFreigeben(redemptionId) {
    this._hass.callService("aufgaben_scoreboard", "approve_redemption", { redemption_id: redemptionId });
  }

  _einloesungAblehnen(redemptionId) {
    this._hass.callService("aufgaben_scoreboard", "reject_redemption", { redemption_id: redemptionId });
  }

  _aufgabeLoeschen(taskId) {
    this._hass.callService("aufgaben_scoreboard", "remove_task", {
      task_id: taskId,
    });
  }

  _neueAufgabeAnlegen(formData) {
    this._hass.callService("aufgaben_scoreboard", "add_task", formData);
  }

  /** Setzt den Punktestand eines Benutzers auf 0 zurück. Nur für Administratoren. */
  _punktestandZuruecksetzen(userId) {
    this._hass.callService("aufgaben_scoreboard", "reset_score", { user_id: userId });
  }

  /**
   * Bearbeitet eine bestehende Aufgabe (Titel/Beschreibung/Punkte und/oder
   * die vollständige Liste der zuständigen Benutzer). "assigned_to" wird
   * dabei komplett ERSETZT (nicht nur ergänzt) - so lassen sich über die
   * Checkbox-Auswahl im Bearbeiten-Formular Benutzer auch wieder abwählen.
   */
  _aufgabeAktualisieren(taskId, formData) {
    this._hass.callService("aufgaben_scoreboard", "update_task", {
      task_id: taskId,
      ...formData,
    });
  }

  _vorlageAnlegen(formData) {
    this._hass.callService("aufgaben_scoreboard", "add_template", formData);
  }

  _vorlageAktualisieren(templateId, formData) {
    this._hass.callService("aufgaben_scoreboard", "update_template", {
      template_id: templateId,
      ...formData,
    });
  }

  _vorlageLoeschen(templateId) {
    this._hass.callService("aufgaben_scoreboard", "remove_template", { template_id: templateId });
  }

  _aufgabeAusVorlageAnlegen(templateId) {
    this._hass.callService("aufgaben_scoreboard", "create_task_from_template", { template_id: templateId });
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
    // Es kann jeweils nur EIN Formular gleichzeitig offen sein (entweder
    // "Neue Aufgabe" ODER die Bearbeitung einer bestehenden Aufgabe) - alle
    // Formulare tragen dafür die gemeinsame Klasse "formular-mit-zustand".
    const formular = this.shadowRoot.querySelector(".formular-mit-zustand");
    if (!formular) return null;

    const aktivesElement = this.shadowRoot.activeElement;
    const werte = {};
    formular.querySelectorAll("input, textarea, select").forEach((feld) => {
      if (!feld.name) return;
      if (feld.type === "checkbox") {
        // Mehrere Checkboxen teilen sich denselben "name" (z. B. für die
        // Zuständigkeits-Auswahl) - alle angehakten Werte werden gesammelt.
        if (!werte[feld.name]) werte[feld.name] = [];
        if (feld.checked) werte[feld.name].push(feld.value);
      } else if (feld.multiple) {
        werte[feld.name] = Array.from(feld.selectedOptions).map((o) => o.value);
      } else {
        werte[feld.name] = feld.value;
      }
    });

    // Trigger-Felder (ha-selector bzw. dessen Text-Fallback) sind keine
    // Standard-Formularelemente mit "name"-Attribut, sondern werden über
    // data-feld-name identifiziert - eigener, einfacherer Durchlauf.
    formular.querySelectorAll("[data-feld-name]").forEach((feld) => {
      werte[feld.dataset.feldName] = feld.value;
    });

    return {
      formularId: formular.id,
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
    const formular = this.shadowRoot.querySelector(".formular-mit-zustand");
    // Nur wiederherstellen, wenn es sich noch um dasselbe Formular handelt
    // (z. B. nicht versehentlich Werte des "Neue Aufgabe"-Formulars auf ein
    // inzwischen geöffnetes Bearbeiten-Formular anwenden).
    if (!formular || formular.id !== zustand.formularId) return;

    formular.querySelectorAll("input, textarea, select").forEach((feld) => {
      if (!feld.name || !(feld.name in zustand.werte)) return;
      const wert = zustand.werte[feld.name];
      if (feld.type === "checkbox") {
        feld.checked = wert.includes(feld.value);
      } else if (feld.multiple) {
        Array.from(feld.options).forEach((option) => {
          option.selected = wert.includes(option.value);
        });
      } else {
        feld.value = wert;
      }
    });

    formular.querySelectorAll("[data-feld-name]").forEach((feld) => {
      const name = feld.dataset.feldName;
      if (name in zustand.werte) {
        feld.value = zustand.werte[name];
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
            // Manche Feldtypen (z. B. number, checkbox) unterstützen
            // setSelectionRange nicht - das ist unkritisch, der Wert
            // selbst bleibt erhalten.
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

    // Tab-Definitionen: "benutzer" ist für ALLE sichtbar, alle
    // anderen nur für Administratoren.
    const tabs = istAdmin
      ? [
          { id: "benutzer", label: "👤 Benutzer" },
          { id: "freigaben", label: "⏳ Freigaben" },
          { id: "verwaltung", label: "📋 Verwaltung" },
          { id: "vorlagen", label: "🔁 Standardaufgaben" },
          { id: "praemien", label: "🎁 Prämien" },
        ]
      : [{ id: "benutzer", label: "👤 Benutzer" }];

    // Falls der zuletzt aktive Tab für die aktuellen Rechte nicht (mehr)
    // existiert (z. B. Admin-Rechte entzogen), sicher auf "benutzer"
    // zurückfallen statt eine leere Seite zu zeigen.
    if (!tabs.some((t) => t.id === this._aktiverTab)) {
      this._aktiverTab = "benutzer";
    }

    this.shadowRoot.innerHTML = `
      <style>${this._css()}</style>
      <div class="wrapper">
        <div class="kopf">
          ${this._isPanel ? `<button class="menu-btn" id="menu-btn" title="Menü">☰</button>` : ""}
          <h1>🏆 Aufgaben-Punktesystem</h1>
        </div>

        ${
          tabs.length > 1
            ? `
          <div class="tab-leiste">
            ${tabs
              .map(
                (t) => `
              <button
                class="tab-btn ${this._aktiverTab === t.id ? "tab-btn-aktiv" : ""}"
                data-tab-id="${t.id}"
              >${t.label}</button>`
              )
              .join("")}
          </div>
        `
            : ""
        }

        ${
          this._aktiverTab === "benutzer"
            ? `
          <div class="abschnitt-kopf-mit-aktion">
            <h2 class="rangliste-titel">🏆 Rangliste</h2>
            ${
              istAdmin
                ? `<button class="btn-primary siegerehrung-btn" title="Ermittelt den/die Gewinner, erhöht deren Sieg-Zähler und setzt alle Punktestände zurück">Siegerehrung durchführen</button>`
                : ""
            }
          </div>

          <div class="rangliste">
            ${benutzerSensoren
              .slice()
              .sort((a, b) => Number(b.zustand.state) - Number(a.zustand.state))
              .map((b) => {
                const userId = b.zustand.attributes.user_id;
                const aufgeklappt = this._aufgeklappterVerlaufUserId === userId;
                const kontoAufgeklappt = this._aufgeklappterPunktekontoUserId === userId;
                const verlauf = b.zustand.attributes.erledigte_aufgaben || [];
                const kontoVerlauf = b.zustand.attributes.punktekonto_verlauf || [];
                const siege = b.zustand.attributes.siege || 0;
                const punktekonto = b.zustand.attributes.punktekonto;
                const menuOffen = this._offenesRangMenuUserId === userId;
                return `
                <div class="rang-eintrag ${userId === eigeneUserId ? "ich" : ""}">
                  <span class="rang-name rang-name-klickbar" data-user-id="${userId}">
                    ${this._escape(b.zustand.attributes.friendly_name || b.entityId)}
                    <span class="verlauf-pfeil">${aufgeklappt ? "▲" : "▼"}</span>
                  </span>
                  <div class="rang-rechts">
                    <div class="rang-badges">
                      <span class="sieg-badge" title="Gewonnene Siegerehrungen">🏆 ${siege}</span>
                      ${
                        punktekonto !== undefined
                          ? `<span class="konto-badge konto-badge-klickbar" data-user-id="${userId}" title="Punktekonto-Verlauf anzeigen">
                              💰 ${punktekonto} <span class="verlauf-pfeil">${kontoAufgeklappt ? "▲" : "▼"}</span>
                            </span>`
                          : ""
                      }
                      <span class="rang-punkte">${b.zustand.state} Pkt.</span>
                      ${
                        istAdmin
                          ? `<div class="rang-menu-wrapper">
                              <button class="rang-menu-btn" data-user-id="${userId}" title="Weitere Aktionen">⋮</button>
                              ${
                                menuOffen
                                  ? `<div class="rang-aktionen rang-aktionen-popup">
                                      <button
                                        class="btn-secondary reset-punkte-btn"
                                        data-user-id="${userId}"
                                        data-user-name="${this._escape(b.zustand.attributes.friendly_name || b.entityId)}"
                                        title="Punktestand zurücksetzen"
                                      >Zurücksetzen</button>
                                      <button
                                        class="btn-secondary reset-siege-btn"
                                        data-user-id="${userId}"
                                        data-user-name="${this._escape(b.zustand.attributes.friendly_name || b.entityId)}"
                                        title="Sieg-Zähler zurücksetzen"
                                      >Siege zurücksetzen</button>
                                      <button
                                        class="btn-danger punkte-abziehen-btn"
                                        data-user-id="${userId}"
                                        data-user-name="${this._escape(b.zustand.attributes.friendly_name || b.entityId)}"
                                        title="Punkte manuell abziehen (z. B. für Fehlverhalten)"
                                      >Punkte abziehen</button>
                                    </div>`
                                  : ""
                              }
                            </div>`
                          : ""
                      }
                    </div>
                  </div>
                </div>
                ${aufgeklappt ? this._renderVerlauf(verlauf, istAdmin) : ""}
                ${kontoAufgeklappt ? this._renderPunktekontoVerlauf(punktekonto, kontoVerlauf) : ""}`;
              })
              .join("")}
          </div>

          <div class="abschnitt">
            <h2>Meine offenen Aufgaben</h2>
            ${this._renderEigeneAufgaben(benutzerSensoren, eigeneUserId)}
          </div>

          ${this._renderMeinPraemienBereich(benutzerSensoren, eigeneUserId, uebersichtsSensor)}
        `
            : ""
        }

        ${
          istAdmin && this._aktiverTab === "freigaben"
            ? `
          ${this._renderFreigabeBereich(uebersichtsSensor, benutzerSensoren)}
          ${this._renderPraemienFreigabeBereich(uebersichtsSensor, benutzerSensoren)}
        `
            : ""
        }
        ${istAdmin && this._aktiverTab === "verwaltung" ? this._renderAdminBereich(uebersichtsSensor, benutzerSensoren) : ""}
        ${istAdmin && this._aktiverTab === "vorlagen" ? this._renderVorlagenBereich(uebersichtsSensor, benutzerSensoren) : ""}
        ${istAdmin && this._aktiverTab === "praemien" ? this._renderPraemienVerwaltungBereich(uebersichtsSensor, benutzerSensoren) : ""}
      </div>
    `;

    // ha-selector-Elemente (Entität/Zustand für den Trigger) sind keine
    // im HTML-Template deklarierbaren Standardelemente - sie müssen nach
    // dem Setzen von innerHTML programmatisch erzeugt und eingebaut
    // werden (siehe _haSelectorenEinbauen()). Der gesicherte
    // Formular-Zustand wird mitgegeben, damit bereits im laufenden
    // Formular getroffene (aber noch nicht gespeicherte) Änderungen -
    // z. B. eine gerade erst ausgewählte oder bewusst gelöschte Entität -
    // beim Neu-Aufbau nicht durch die alten, gespeicherten Vorlagendaten
    // überschrieben werden.
    this._haSelectorenEinbauen(uebersichtsSensor, gesicherterFormularZustand);

    this._eventListenerRegistrieren(istAdmin, benutzerSensoren);

    // Gesicherte Formularwerte + Fokus wiederherstellen (falls das
    // Formular offen war und Re-Render trotzdem stattgefunden hat).
    this._stelleFormularZustandWieder(gesicherterFormularZustand);

    // Sichtbarkeit der Zeitplan-Unterfelder (Intervall/Wochentag) an den
    // ggf. gerade wiederhergestellten Auswahlwert anpassen - siehe
    // _vorlagenZeitplanUiAktualisieren().
    this._vorlagenZeitplanUiAktualisieren();
  }

  _renderEigeneAufgaben(benutzerSensoren, eigeneUserId) {
    const eigener = benutzerSensoren.find((b) => b.zustand.attributes.user_id === eigeneUserId);
    const aufgaben = eigener ? eigener.zustand.attributes.offene_aufgaben : [];
    const wartende = eigener ? eigener.zustand.attributes.wartende_aufgaben : [];

    const offenListe =
      !aufgaben || aufgaben.length === 0
        ? `<div class="hinweis">Keine offenen Aufgaben für dich. 🎉</div>`
        : `
      <div class="aufgaben-liste">
        ${aufgaben
          .map(
            (a) => `
          <div class="aufgaben-karte ${a.ist_ueberfaellig ? "aufgaben-karte-ueberfaellig" : ""}">
            <div class="aufgaben-info">
              <div class="aufgaben-name">${this._escape(a.name)}</div>
              ${a.description ? `<div class="aufgaben-beschreibung">${this._escape(a.description)}</div>` : ""}
              ${
                a.due_at
                  ? `<div class="faelligkeit-hinweis ${a.ist_ueberfaellig ? "faelligkeit-ueberfaellig" : ""}">
                      ${a.ist_ueberfaellig ? "⚠️ Überfällig seit" : "📅 Fällig am"} ${this._formatiereReinesDatum(a.due_at)}
                    </div>`
                  : ""
              }
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

    const wartendListe =
      wartende && wartende.length > 0
        ? `
      <div class="aufgaben-liste wartend-liste">
        ${wartende
          .map(
            (a) => `
          <div class="aufgaben-karte wartend">
            <div class="aufgaben-info">
              <div class="aufgaben-name">${this._escape(a.name)}</div>
              <div class="aufgaben-beschreibung">⏳ Wartet auf Freigabe durch einen Administrator</div>
            </div>
            <div class="aufgaben-aktion">
              <span class="punkte-badge punkte-badge-wartend">+${a.score}</span>
            </div>
          </div>`
          )
          .join("")}
      </div>
    `
        : "";

    return offenListe + wartendListe;
  }

  /**
   * Rendert den aufklappbaren Erledigungs-Verlauf eines einzelnen
   * Benutzers unterhalb seines Rangliste-Eintrags. Das "ruecknehmbar"-
   * Flag jedes Eintrags kommt bereits fertig berechnet vom Server
   * (siehe AufgabenScoreboardManager.get_completed_tasks_for_user) -
   * das Frontend muss die Zeit-/Mengen-Grenze nicht selbst nachbauen.
   */
  _renderVerlauf(verlauf, istAdmin) {
    if (!verlauf || verlauf.length === 0) {
      return `<div class="verlauf-bereich"><div class="hinweis-klein">Noch keine erledigten Aufgaben.</div></div>`;
    }

    return `
      <div class="verlauf-bereich">
        ${verlauf
          .map(
            (eintrag) => `
          <div class="verlauf-eintrag">
            <div class="verlauf-info">
              <span class="verlauf-name">${this._escape(eintrag.task_name)}</span>
              <span class="verlauf-datum">${this._formatiereDatum(eintrag.completed_at)}</span>
            </div>
            <div class="verlauf-aktion">
              <span class="punkte-badge">+${eintrag.score}</span>
              ${
                istAdmin
                  ? eintrag.ruecknehmbar
                    ? `<button class="btn-danger rueckgaengig-btn" data-completion-id="${eintrag.completion_id}" data-task-name="${this._escape(eintrag.task_name)}">Rückgängig</button>`
                    : `<span class="hinweis-klein">nicht mehr rücknehmbar</span>`
                  : ""
              }
            </div>
          </div>`
          )
          .join("")}
      </div>
    `;
  }

  /**
   * Eigenständiger, aufklappbarer Punktekonto-Verlauf (bewusst getrennt
   * von _renderVerlauf() oben, das die erledigten AUFGABEN zeigt) -
   * listet Zugänge (Siegerehrung) und Abgänge (Prämien-Einlösung) in
   * chronologischer Reihenfolge.
   */
  _renderPunktekontoVerlauf(guthaben, verlauf) {
    return `
      <div class="verlauf-bereich konto-verlauf-bereich">
        <div class="konto-verlauf-guthaben">💰 Aktuelles Guthaben: ${guthaben} Punkte</div>
        ${
          !verlauf || verlauf.length === 0
            ? `<div class="hinweis-klein">Noch keine Punktekonto-Bewegungen.</div>`
            : verlauf
                .map(
                  (eintrag) => `
          <div class="verlauf-eintrag">
            <div class="verlauf-info">
              <span class="verlauf-name">${this._escape(eintrag.reason)}</span>
              <span class="verlauf-datum">${this._formatiereDatum(eintrag.timestamp)}</span>
            </div>
            <div class="verlauf-aktion">
              <span class="punkte-badge ${eintrag.amount < 0 ? "punkte-badge-abgang" : ""}">
                ${eintrag.amount > 0 ? "+" : ""}${eintrag.amount}
              </span>
            </div>
          </div>`
                )
                .join("")
        }
      </div>
    `;
  }

  /** Formatiert einen ISO-8601-Zeitstempel als lesbares Datum (TT.MM.JJJJ, hh:mm). */
  _formatiereDatum(isoZeitstempel) {
    try {
      const datum = new Date(isoZeitstempel);
      return datum.toLocaleString("de-DE", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (fehler) {
      return isoZeitstempel;
    }
  }

  /** Formatiert ein reines ISO-Datum (YYYY-MM-DD, ohne Uhrzeit) als TT.MM.JJJJ - für due_at (Fälligkeit hat keine Uhrzeit). */
  _formatiereReinesDatum(isoDatum) {
    try {
      const [jahr, monat, tag] = isoDatum.split("-");
      return `${tag}.${monat}.${jahr}`;
    } catch (fehler) {
      return isoDatum;
    }
  }

  /**
   * Admin-Bereich "Wartet auf Freigabe": alle Aufgaben, die irgendein
   * Benutzer als erledigt gemeldet hat, aber noch nicht bestätigt
   * wurden. Wird nur für Administratoren gerendert.
   */
  _renderFreigabeBereich(uebersichtsSensor, benutzerSensoren) {
    const wartende = uebersichtsSensor ? uebersichtsSensor.attributes.wartende_aufgaben || [] : [];

    return `
      <div class="abschnitt admin-bereich">
        <h2>⏳ Wartet auf Freigabe${wartende.length > 0 ? ` (${wartende.length})` : ""}</h2>
        ${
          wartende.length === 0
            ? `<div class="hinweis">Aktuell nichts zu prüfen.</div>`
            : `
          <div class="aufgaben-liste">
            ${wartende
              .map(
                (a) => `
              <div class="aufgaben-karte">
                <div class="aufgaben-info">
                  <div class="aufgaben-name">${this._escape(a.name)}</div>
                  ${a.description ? `<div class="aufgaben-beschreibung">${this._escape(a.description)}</div>` : ""}
                  <div class="aufgaben-zuweisung">
                    Gemeldet von: ${this._nameFuerUserId(a.pending_by, benutzerSensoren)}
                    · ${this._formatiereDatum(a.pending_since)}
                  </div>
                </div>
                <div class="aufgaben-aktion">
                  <span class="punkte-badge">+${a.score}</span>
                  <button class="btn-primary freigeben-btn" data-task-id="${a.id}">Freigeben</button>
                  <button class="btn-danger ablehnen-btn" data-task-id="${a.id}">Ablehnen</button>
                </div>
              </div>`
              )
              .join("")}
          </div>
        `
        }
      </div>
    `;
  }

  /**
   * Persönlicher Bereich "Mein Punktekonto": Guthaben + verfügbare
   * Prämien mit Einlösen-Button. Wird nur angezeigt, wenn das
   * Prämien-System aktiviert ist (erkennbar daran, dass der eigene
   * Sensor überhaupt ein "punktekonto"-Attribut besitzt - fehlt es,
   * ist das Feature serverseitig deaktiviert, siehe sensor.py).
   */
  _renderMeinPraemienBereich(benutzerSensoren, eigeneUserId, uebersichtsSensor) {
    const eigener = benutzerSensoren.find((b) => b.zustand.attributes.user_id === eigeneUserId);
    if (!eigener || eigener.zustand.attributes.punktekonto === undefined) {
      return "";
    }
    const guthaben = eigener.zustand.attributes.punktekonto;
    const praemien = uebersichtsSensor ? uebersichtsSensor.attributes.praemien || [] : [];

    return `
      <div class="abschnitt">
        <h2>💰 Mein Punktekonto: ${guthaben} Punkte</h2>
        ${
          praemien.length === 0
            ? `<div class="hinweis">Noch keine Prämien verfügbar.</div>`
            : `
          <div class="aufgaben-liste">
            ${praemien
              .map((p) => {
                const leistbar = guthaben >= p.cost;
                return `
              <div class="aufgaben-karte ${leistbar ? "" : "wartend"}">
                <div class="aufgaben-info">
                  <div class="aufgaben-name">${this._escape(p.name)}</div>
                  ${p.description ? `<div class="aufgaben-beschreibung">${this._escape(p.description)}</div>` : ""}
                  ${p.reward_type === "internet_time" ? `<div class="aufgaben-beschreibung">⏱️ ${p.duration_minutes} Minuten Internet-Zeit</div>` : ""}
                </div>
                <div class="aufgaben-aktion">
                  <span class="punkte-badge">${p.cost} Pkt.</span>
                  <button
                    class="btn-primary praemie-einloesen-btn"
                    data-reward-id="${p.id}"
                    data-reward-name="${this._escape(p.name)}"
                    ${leistbar ? "" : "disabled"}
                  >Einlösen</button>
                </div>
              </div>`;
              })
              .join("")}
          </div>
        `
        }
      </div>
    `;
  }

  /** Admin-Bereich "Wartet auf Freigabe (Prämien)": angefragte Einlösungen, die noch bestätigt werden müssen. */
  _renderPraemienFreigabeBereich(uebersichtsSensor, benutzerSensoren) {
    if (!uebersichtsSensor || uebersichtsSensor.attributes.praemien === undefined) {
      return "";
    }
    const wartende = uebersichtsSensor.attributes.wartende_praemien || [];

    return `
      <div class="abschnitt admin-bereich">
        <h2>🎁 Prämien-Einlösungen zur Freigabe${wartende.length > 0 ? ` (${wartende.length})` : ""}</h2>
        ${
          wartende.length === 0
            ? `<div class="hinweis">Aktuell nichts zu prüfen.</div>`
            : `
          <div class="aufgaben-liste">
            ${wartende
              .map(
                (r) => `
              <div class="aufgaben-karte">
                <div class="aufgaben-info">
                  <div class="aufgaben-name">${this._escape(r.reward_name)}</div>
                  <div class="aufgaben-zuweisung">
                    Angefragt von: ${this._nameFuerUserId(r.user_id, benutzerSensoren)}
                    · ${this._formatiereDatum(r.requested_at)}
                  </div>
                </div>
                <div class="aufgaben-aktion">
                  <span class="punkte-badge">${r.cost} Pkt.</span>
                  <button class="btn-primary freigeben-praemie-btn" data-redemption-id="${r.redemption_id}">Freigeben</button>
                  <button class="btn-danger ablehnen-praemie-btn" data-redemption-id="${r.redemption_id}">Ablehnen</button>
                </div>
              </div>`
              )
              .join("")}
          </div>
        `
        }
      </div>
    `;
  }

  /** Admin-Bereich "Prämien verwalten": Liste + Formular zum Anlegen/Bearbeiten von Prämien. */
  _renderPraemienVerwaltungBereich(uebersichtsSensor, benutzerSensoren) {
    if (!uebersichtsSensor || uebersichtsSensor.attributes.praemien === undefined) {
      return "";
    }
    const praemien = uebersichtsSensor.attributes.praemien || [];

    const bearbeitetePraemie = this._bearbeitePraemieId
      ? praemien.find((p) => p.id === this._bearbeitePraemieId)
      : null;
    if (this._bearbeitePraemieId && !bearbeitetePraemie) {
      this._bearbeitePraemieId = null;
    }

    const formularId = bearbeitetePraemie ? "praemie-bearbeiten-formular" : "neue-praemie-formular";
    const formularTitel = bearbeitetePraemie ? "Prämie bearbeiten" : "Neue Prämie anlegen";
    const buttonBeschriftung = bearbeitetePraemie ? "Änderungen speichern" : "Prämie anlegen";
    const typWert = bearbeitetePraemie ? bearbeitetePraemie.reward_type : "generic";

    return `
      <div class="abschnitt admin-bereich">
        <div class="admin-kopf">
          <h2>🎁 Prämien verwalten</h2>
          <button class="btn-secondary" id="toggle-praemien-formular">
            ${this._praemienFormularOffen ? "Formular schließen" : "+ Neue Prämie"}
          </button>
        </div>

        ${
          this._praemienFormularOffen
            ? `
          <form class="neue-aufgabe-formular formular-mit-zustand" id="${formularId}">
            <h3 class="formular-titel">${formularTitel}</h3>
            <label>
              Titel
              <input
                type="text"
                name="name"
                required
                placeholder="z. B. Kinobesuch"
                value="${bearbeitetePraemie ? this._escape(bearbeitetePraemie.name) : ""}"
              />
            </label>
            <label>
              Beschreibung (optional)
              <textarea name="description" placeholder="Details zur Prämie">${
                bearbeitetePraemie ? this._escape(bearbeitetePraemie.description || "") : ""
              }</textarea>
            </label>
            <label>
              Preis (Punkte)
              <input
                type="number"
                name="cost"
                min="0"
                required
                value="${bearbeitetePraemie ? bearbeitetePraemie.cost : 10}"
              />
            </label>
            <label>
              Typ
              <select name="reward_type" id="praemie-typ-auswahl">
                <option value="generic" ${typWert === "generic" ? "selected" : ""}>Generisch (nur Protokollierung)</option>
                <option value="internet_time" ${typWert === "internet_time" ? "selected" : ""}>Internet-Zeit (schaltet eine Entität)</option>
              </select>
            </label>
            <div class="internet-zeit-felder" style="${typWert === "internet_time" ? "" : "display:none;"}">
              <label>
                Zu schaltende Entität (switch)
                <input
                  type="text"
                  name="switch_entity_id"
                  placeholder="z. B. switch.kind_wlan"
                  value="${bearbeitetePraemie ? this._escape(bearbeitetePraemie.switch_entity_id || "") : ""}"
                />
              </label>
              <label>
                Dauer (Minuten)
                <input
                  type="number"
                  name="duration_minutes"
                  min="1"
                  value="${bearbeitetePraemie && bearbeitetePraemie.duration_minutes ? bearbeitetePraemie.duration_minutes : 30}"
                />
              </label>
            </div>
            <div class="formular-aktionen">
              <button type="submit" class="btn-primary">${buttonBeschriftung}</button>
              ${
                bearbeitetePraemie
                  ? `<button type="button" class="btn-secondary" id="praemie-bearbeiten-abbrechen">Abbrechen</button>`
                  : ""
              }
            </div>
          </form>
        `
            : ""
        }

        <div class="aufgaben-liste">
          ${
            praemien.length === 0
              ? `<div class="hinweis">Noch keine Prämien angelegt.</div>`
              : praemien
                  .map(
                    (p) => `
              <div class="aufgaben-karte">
                <div class="aufgaben-info">
                  <div class="aufgaben-name">${this._escape(p.name)}</div>
                  ${p.description ? `<div class="aufgaben-beschreibung">${this._escape(p.description)}</div>` : ""}
                  <div class="vorlage-badges">
                    <span class="vorlage-badge">${p.reward_type === "internet_time" ? "⏱️ Internet-Zeit" : "🎫 Generisch"}</span>
                  </div>
                </div>
                <div class="aufgaben-aktion">
                  <span class="punkte-badge">${p.cost} Pkt.</span>
                  <button class="btn-secondary praemie-bearbeiten-btn" data-reward-id="${p.id}">Bearbeiten</button>
                  <button class="btn-danger praemie-loeschen-btn" data-reward-id="${p.id}">Löschen</button>
                </div>
              </div>`
                  )
                  .join("")
          }
        </div>
      </div>
    `;
  }

  _renderAdminBereich(uebersichtsSensor, benutzerSensoren) {
    const alleAufgaben = uebersichtsSensor ? uebersichtsSensor.attributes.alle_aufgaben : [];
    const offeneAufgaben = alleAufgaben.filter((a) => a.status === "open");

    // Wird gerade eine bestehende Aufgabe bearbeitet, deren Daten für die
    // Vorbelegung des Formulars heraussuchen. Existiert die Aufgabe nicht
    // mehr (z. B. zwischenzeitlich von jemand anderem gelöscht), sauber
    // in den "Neue Aufgabe"-Modus zurückfallen.
    const bearbeiteteAufgabe = this._bearbeiteTaskId
      ? alleAufgaben.find((a) => a.id === this._bearbeiteTaskId)
      : null;
    if (this._bearbeiteTaskId && !bearbeiteteAufgabe) {
      this._bearbeiteTaskId = null;
    }

    const formularId = bearbeiteteAufgabe ? "aufgabe-bearbeiten-formular" : "neue-aufgabe-formular";
    const formularTitel = bearbeiteteAufgabe ? "Aufgabe bearbeiten" : "Neue Aufgabe anlegen";
    const buttonBeschriftung = bearbeiteteAufgabe ? "Änderungen speichern" : "Aufgabe anlegen";
    const vorbelegteBenutzer = bearbeiteteAufgabe ? bearbeiteteAufgabe.assigned_to || [] : [];

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
          <form class="neue-aufgabe-formular formular-mit-zustand" id="${formularId}">
            <h3 class="formular-titel">${formularTitel}</h3>
            <label>
              Titel
              <input
                type="text"
                name="name"
                required
                placeholder="z. B. Rasen mähen"
                value="${bearbeiteteAufgabe ? this._escape(bearbeiteteAufgabe.name) : ""}"
              />
            </label>
            <label>
              Beschreibung (optional)
              <textarea name="description" placeholder="Details zur Aufgabe">${
                bearbeiteteAufgabe ? this._escape(bearbeiteteAufgabe.description || "") : ""
              }</textarea>
            </label>
            <label>
              Punkte
              <input
                type="number"
                name="score"
                min="0"
                required
                value="${bearbeiteteAufgabe ? bearbeiteteAufgabe.score : 10}"
              />
            </label>
            <fieldset class="zustaendigkeit-feld">
              <legend>Zuständig (Mehrfachauswahl, leer = für alle offen)</legend>
              ${this._renderBenutzerCheckboxen(benutzerSensoren, vorbelegteBenutzer)}
            </fieldset>
            <label>
              Fällig in X Tagen (optional)
              <input
                type="number"
                name="due_in_days"
                min="0"
                placeholder="z. B. 3"
                value="${
                  bearbeiteteAufgabe && bearbeiteteAufgabe.due_in_days !== null && bearbeiteteAufgabe.due_in_days !== undefined
                    ? bearbeiteteAufgabe.due_in_days
                    : ""
                }"
              />
            </label>
            <label>
              Erinnerung nach X Tagen offen (optional)
              <input
                type="number"
                name="reminder_days"
                min="1"
                placeholder="z. B. 2"
                value="${
                  bearbeiteteAufgabe && bearbeiteteAufgabe.reminder_days !== null && bearbeiteteAufgabe.reminder_days !== undefined
                    ? bearbeiteteAufgabe.reminder_days
                    : ""
                }"
              />
            </label>
            <div class="formular-aktionen">
              <button type="submit" class="btn-primary">${buttonBeschriftung}</button>
              ${
                bearbeiteteAufgabe
                  ? `<button type="button" class="btn-secondary" id="bearbeiten-abbrechen">Abbrechen</button>`
                  : ""
              }
            </div>
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
              <div class="aufgaben-karte ${a.ist_ueberfaellig ? "aufgaben-karte-ueberfaellig" : ""}">
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
                  ${
                    a.due_at
                      ? `<div class="faelligkeit-hinweis ${a.ist_ueberfaellig ? "faelligkeit-ueberfaellig" : ""}">
                          ${a.ist_ueberfaellig ? "⚠️ Überfällig seit" : "📅 Fällig am"} ${this._formatiereReinesDatum(a.due_at)}
                        </div>`
                      : ""
                  }
                </div>
                <div class="aufgaben-aktion">
                  <span class="punkte-badge">+${a.score}</span>
                  <button class="btn-secondary bearbeiten-btn" data-task-id="${a.id}">Bearbeiten</button>
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

  /**
   * Rendert eine Checkbox pro (konfiguriertem) Benutzer für die
   * Zuständigkeits-Auswahl einer Aufgabe. Ersetzt das frühere
   * Einzel-Auswahl-Dropdown: so lassen sich mehrere Zuständige auf einen
   * Blick erkennen, gezielt hinzufügen UND wieder abwählen.
   */
  _renderBenutzerCheckboxen(benutzerSensoren, ausgewaehlteIds) {
    if (!benutzerSensoren.length) {
      return `<div class="hinweis-klein">
        Keine Benutzer verfügbar. Unter "Einstellungen -&gt; Geräte &amp; Dienste ->
        Aufgaben-Punktesystem -> Konfigurieren" lässt sich auswählen, welche
        Benutzer hier berücksichtigt werden.
      </div>`;
    }

    return benutzerSensoren
      .map((b) => {
        const userId = b.zustand.attributes.user_id;
        const name = this._escape(b.zustand.attributes.friendly_name || b.entityId);
        const checked = ausgewaehlteIds.includes(userId) ? "checked" : "";
        return `
          <label class="benutzer-checkbox">
            <input type="checkbox" name="assigned_to" value="${userId}" ${checked} />
            <span>${name}</span>
          </label>`;
      })
      .join("");
  }

  _nameFuerUserId(userId, benutzerSensoren) {
    const treffer = benutzerSensoren.find((b) => b.zustand.attributes.user_id === userId);
    return treffer ? this._escape(treffer.zustand.attributes.friendly_name || userId) : userId;
  }

  /** Baut eine kurze, lesbare Beschreibung des Zeitplans einer Vorlage für das Badge (z. B. "Alle 2 Wochen am Mittwoch"). */
  _zeitplanBeschreibung(vorlage) {
    const wochentagsNamen = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];
    const intervall = vorlage.schedule_interval || 1;
    if (vorlage.schedule_type === "days") {
      return intervall === 1 ? "Täglich" : `Alle ${intervall} Tage`;
    }
    if (vorlage.schedule_type === "weekly") {
      const wochentag = wochentagsNamen[vorlage.schedule_weekday] || "?";
      return intervall === 1 ? `Jede Woche am ${wochentag}` : `Alle ${intervall} Wochen am ${wochentag}`;
    }
    return "";
  }

  /**
   * Admin-Bereich "Standardaufgaben" (Vorlagen): Liste + Formular zum
   * Anlegen/Bearbeiten. Nutzt bewusst dieselben Formular-Feldnamen wie
   * das Aufgaben-Formular (name/description/score/assigned_to) - da
   * sich Aufgaben- und Vorlagen-Formular gegenseitig ausschließen
   * (siehe Konstruktor-Kommentar), gibt es dabei keine Kollision.
   */
  _renderVorlagenBereich(uebersichtsSensor, benutzerSensoren) {
    const vorlagen = uebersichtsSensor ? uebersichtsSensor.attributes.vorlagen || [] : [];

    const bearbeiteteVorlage = this._bearbeiteVorlageId
      ? vorlagen.find((v) => v.id === this._bearbeiteVorlageId)
      : null;
    if (this._bearbeiteVorlageId && !bearbeiteteVorlage) {
      this._bearbeiteVorlageId = null;
    }

    const formularId = bearbeiteteVorlage ? "vorlage-bearbeiten-formular" : "neue-vorlage-formular";
    const formularTitel = bearbeiteteVorlage ? "Standardaufgabe bearbeiten" : "Neue Standardaufgabe anlegen";
    const buttonBeschriftung = bearbeiteteVorlage ? "Änderungen speichern" : "Standardaufgabe anlegen";
    const vorbelegteBenutzer = bearbeiteteVorlage ? bearbeiteteVorlage.assigned_to || [] : [];

    // Zeitplan-Vorbelegung: das Dropdown "schedule_type_ui" ist eine reine
    // UI-Auswahl mit VIER Optionen ("", "days", "weekly_single",
    // "weekly_interval"), die beim Absenden auf die ZWEI tatsächlichen
    // Backend-Werte (schedule_type "days"/"weekly" + schedule_interval)
    // abgebildet wird - siehe _vorlagenFormularAbsenden().
    let zeitplanTypUiWert = "";
    let zeitplanIntervallWert = 1;
    let zeitplanWochentagWert = 0;
    if (bearbeiteteVorlage && bearbeiteteVorlage.schedule_type === "days") {
      zeitplanTypUiWert = "days";
      zeitplanIntervallWert = bearbeiteteVorlage.schedule_interval || 1;
    } else if (bearbeiteteVorlage && bearbeiteteVorlage.schedule_type === "weekly") {
      zeitplanIntervallWert = bearbeiteteVorlage.schedule_interval || 1;
      zeitplanWochentagWert = bearbeiteteVorlage.schedule_weekday != null ? bearbeiteteVorlage.schedule_weekday : 0;
      zeitplanTypUiWert = zeitplanIntervallWert > 1 ? "weekly_interval" : "weekly_single";
    }
    const zeitplanWochentage = [
      ["0", "Montag"],
      ["1", "Dienstag"],
      ["2", "Mittwoch"],
      ["3", "Donnerstag"],
      ["4", "Freitag"],
      ["5", "Samstag"],
      ["6", "Sonntag"],
    ];

    return `
      <div class="abschnitt admin-bereich">
        <div class="admin-kopf">
          <h2>Standardaufgaben</h2>
          <button class="btn-secondary" id="toggle-vorlagen-formular">
            ${this._vorlagenFormularOffen ? "Formular schließen" : "+ Neue Standardaufgabe"}
          </button>
        </div>

        ${
          this._vorlagenFormularOffen
            ? `
          <form class="neue-aufgabe-formular formular-mit-zustand" id="${formularId}">
            <h3 class="formular-titel">${formularTitel}</h3>
            <label>
              Titel
              <input
                type="text"
                name="name"
                required
                placeholder="z. B. Rasen mähen"
                value="${bearbeiteteVorlage ? this._escape(bearbeiteteVorlage.name) : ""}"
              />
            </label>
            <label>
              Beschreibung (optional)
              <textarea name="description" placeholder="Details zur Aufgabe">${
                bearbeiteteVorlage ? this._escape(bearbeiteteVorlage.description || "") : ""
              }</textarea>
            </label>
            <label>
              Punkte
              <input
                type="number"
                name="score"
                min="0"
                required
                value="${bearbeiteteVorlage ? bearbeiteteVorlage.score : 10}"
              />
            </label>
            <fieldset class="zustaendigkeit-feld">
              <legend>Zuständig (Mehrfachauswahl, leer = für alle offen)</legend>
              ${this._renderBenutzerCheckboxen(benutzerSensoren, vorbelegteBenutzer)}
            </fieldset>
            <label class="multiscoring-feld">
              <input
                type="checkbox"
                name="multiscoring"
                ${bearbeiteteVorlage && bearbeiteteVorlage.multiscoring ? "checked" : ""}
              />
              <span>
                Multiscoring – jeder zugewiesene Benutzer bekommt beim Anlegen eine
                eigene, unabhängig erledigbare Aufgabe (statt einer gemeinsamen).
                Erfordert mindestens einen zugewiesenen Benutzer.
              </span>
            </label>
            <fieldset class="trigger-feld">
              <legend>Automatische Anlage per Entität (optional)</legend>
              <div class="ha-selector-slot" data-feld="trigger_entity_id"></div>
              <div class="ha-selector-slot" data-feld="trigger_from_state"></div>
              <div class="ha-selector-slot" data-feld="trigger_state"></div>
              <label>
                Wert über (optional)
                <input
                  type="number"
                  step="any"
                  name="trigger_above"
                  placeholder="z. B. 25"
                  value="${
                    bearbeiteteVorlage && bearbeiteteVorlage.trigger_above !== null && bearbeiteteVorlage.trigger_above !== undefined
                      ? bearbeiteteVorlage.trigger_above
                      : ""
                  }"
                />
              </label>
              <label>
                Wert unter (optional)
                <input
                  type="number"
                  step="any"
                  name="trigger_below"
                  placeholder="z. B. 10"
                  value="${
                    bearbeiteteVorlage && bearbeiteteVorlage.trigger_below !== null && bearbeiteteVorlage.trigger_below !== undefined
                      ? bearbeiteteVorlage.trigger_below
                      : ""
                  }"
                />
              </label>
              <div class="hinweis-klein">
                Wie beim Zustands-Trigger im Automationen-Editor: "Von"
                und "Zu" prüfen den exakten Zustandstext (beide optional,
                "Von" nur sinnvoll zusammen mit "Zu"). "Über"/"Unter"
                vergleichen den Zustand als Zahl und sind unabhängig
                davon nutzbar - auch gleichzeitig, für einen Wertebereich.
                Automatische Anlage nur, sofern nicht bereits eine offene
                Aufgabe aus dieser Vorlage existiert.
              </div>
            </fieldset>
            <fieldset class="zeitplan-feld">
              <legend>Automatische Anlage per Zeitplan (optional)</legend>
              <label>
                Wiederholung
                <select name="schedule_type_ui" class="zeitplan-typ-auswahl">
                  <option value="" ${zeitplanTypUiWert === "" ? "selected" : ""}>Kein Zeitplan</option>
                  <option value="days" ${zeitplanTypUiWert === "days" ? "selected" : ""}>Alle X Tage</option>
                  <option value="weekly_single" ${
                    zeitplanTypUiWert === "weekly_single" ? "selected" : ""
                  }>Jede Woche am Wochentag</option>
                  <option value="weekly_interval" ${
                    zeitplanTypUiWert === "weekly_interval" ? "selected" : ""
                  }>Alle X Wochen am Wochentag</option>
                </select>
              </label>
              <label class="zeitplan-intervall-feld" data-zeitplan-zeile="interval">
                Alle
                <input type="number" name="schedule_interval" min="1" value="${zeitplanIntervallWert}" />
                <span class="zeitplan-einheit-label">${zeitplanTypUiWert === "weekly_interval" ? "Wochen" : "Tage"}</span>
              </label>
              <label class="zeitplan-wochentag-feld" data-zeitplan-zeile="weekday">
                Wochentag
                <select name="schedule_weekday">
                  ${zeitplanWochentage
                    .map(
                      ([wert, bezeichnung]) =>
                        `<option value="${wert}" ${
                          String(zeitplanWochentagWert) === wert ? "selected" : ""
                        }>${bezeichnung}</option>`
                    )
                    .join("")}
                </select>
              </label>
              <div class="hinweis-klein">
                Erzeugt automatisch eine neue Aufgabe nach dem gewählten
                Zeitplan - sofern nicht bereits eine offene Aufgabe aus
                dieser Vorlage existiert. Kann zusätzlich zum
                Entitäts-Trigger oder unabhängig davon genutzt werden.
              </div>
            </fieldset>
            <label>
              Fällig in X Tagen (optional)
              <input
                type="number"
                name="due_in_days"
                min="0"
                placeholder="z. B. 3"
                value="${
                  bearbeiteteVorlage && bearbeiteteVorlage.due_in_days !== null && bearbeiteteVorlage.due_in_days !== undefined
                    ? bearbeiteteVorlage.due_in_days
                    : ""
                }"
              />
            </label>
            <label>
              Erinnerung nach X Tagen offen (optional)
              <input
                type="number"
                name="reminder_days"
                min="1"
                placeholder="z. B. 2"
                value="${
                  bearbeiteteVorlage && bearbeiteteVorlage.reminder_days !== null && bearbeiteteVorlage.reminder_days !== undefined
                    ? bearbeiteteVorlage.reminder_days
                    : ""
                }"
              />
            </label>
            <div class="formular-aktionen">
              <button type="submit" class="btn-primary">${buttonBeschriftung}</button>
              ${
                bearbeiteteVorlage
                  ? `<button type="button" class="btn-secondary" id="vorlage-bearbeiten-abbrechen">Abbrechen</button>`
                  : ""
              }
            </div>
          </form>
        `
            : ""
        }

        <div class="aufgaben-liste">
          ${
            vorlagen.length === 0
              ? `<div class="hinweis">Noch keine Standardaufgaben angelegt.</div>`
              : vorlagen
                  .map(
                    (v) => `
              <div class="aufgaben-karte">
                <div class="aufgaben-info">
                  <div class="aufgaben-name">${this._escape(v.name)}</div>
                  ${v.description ? `<div class="aufgaben-beschreibung">${this._escape(v.description)}</div>` : ""}
                  <div class="aufgaben-zuweisung">
                    Zuständig: ${
                      v.assigned_to && v.assigned_to.length
                        ? v.assigned_to.map((uid) => this._nameFuerUserId(uid, benutzerSensoren)).join(", ")
                        : "Alle Benutzer"
                    }
                  </div>
                  <div class="vorlage-badges">
                    ${v.multiscoring ? `<span class="vorlage-badge">🔁 Multiscoring</span>` : ""}
                    ${
                      v.trigger_entity_id
                        ? `<span class="vorlage-badge">⚡ ${this._escape(v.trigger_entity_id)} = ${this._escape(
                            v.trigger_state
                          )}</span>`
                        : ""
                    }
                    ${v.schedule_type ? `<span class="vorlage-badge">📅 ${this._escape(this._zeitplanBeschreibung(v))}</span>` : ""}
                  </div>
                </div>
                <div class="aufgaben-aktion">
                  <span class="punkte-badge">+${v.score}</span>
                  <button class="btn-primary vorlage-anlegen-btn" data-template-id="${v.id}">Jetzt anlegen</button>
                  <button class="btn-secondary vorlage-bearbeiten-btn" data-template-id="${v.id}">Bearbeiten</button>
                  <button class="btn-danger vorlage-loeschen-btn" data-template-id="${v.id}">Löschen</button>
                </div>
              </div>`
                  )
                  .join("")
          }
        </div>
      </div>
    `;
  }

  /**
   * Baut die ha-selector-Elemente für Trigger-Entität und Ziel-Zustand
   * in das Vorlagen-Formular ein - programmatisch, da ha-selector über
   * JS-Eigenschaften (.hass/.selector/.value) konfiguriert wird und
   * nicht als reines HTML-Attribut im Template-String deklariert werden
   * kann. ha-selector/ha-entity-picker sind Teil des HA-Frontend-Bundles
   * und als Custom Elements bereits global registriert - exakt dieselbe
   * Komponente, die auch der eingebaute Automationen-Editor für
   * Trigger nutzt (inkl. Zustands-Vorschlägen für die gewählte Entität).
   *
   * Fällt auf einfache Textfelder zurück, falls ha-selector aus
   * irgendeinem Grund nicht verfügbar sein sollte (defensive
   * Absicherung, sollte in der Praxis nicht vorkommen).
   */
  _haSelectorenEinbauen(uebersichtsSensor, gesicherterFormularZustand) {
    const entitySlot = this.shadowRoot.querySelector('.ha-selector-slot[data-feld="trigger_entity_id"]');
    const fromStateSlot = this.shadowRoot.querySelector('.ha-selector-slot[data-feld="trigger_from_state"]');
    const stateSlot = this.shadowRoot.querySelector('.ha-selector-slot[data-feld="trigger_state"]');
    if (!entitySlot || !fromStateSlot || !stateSlot) return;

    const vorlagen = uebersichtsSensor ? uebersichtsSensor.attributes.vorlagen || [] : [];
    const bearbeiteteVorlage = this._bearbeiteVorlageId
      ? vorlagen.find((v) => v.id === this._bearbeiteVorlageId)
      : null;

    // Startwerte: zunächst aus der zuletzt GESPEICHERTEN Vorlage (Server-
    // Daten) - das ist der richtige Ausgangspunkt beim allerersten Öffnen
    // des Formulars.
    let entityWert = bearbeiteteVorlage ? bearbeiteteVorlage.trigger_entity_id || "" : "";
    let fromStateWert = bearbeiteteVorlage ? bearbeiteteVorlage.trigger_from_state || "" : "";
    let stateWert = bearbeiteteVorlage ? bearbeiteteVorlage.trigger_state || "" : "";

    // WICHTIG: Ist bereits ein Formular-Zustand für GENAU dieses Formular
    // gesichert (z. B. weil dieses Re-Render durch eine Eingabe im
    // laufenden Formular selbst ausgelöst wurde - Entität ausgewählt,
    // Entität wieder gelöscht, ...), hat dieser IMMER Vorrang vor den
    // alten Server-Daten. Ohne diese Vorrangregel würde z. B. das
    // Löschen der Entitäts-Auswahl beim direkt folgenden Re-Render sofort
    // wieder mit dem alten, gespeicherten Wert überschrieben werden - der
    // Status-Selector würde zudem die Zustände der FALSCHEN (alten)
    // Entität vorschlagen, statt die der gerade neu gewählten.
    const aktuellesFormularId = this.shadowRoot.querySelector(".formular-mit-zustand")?.id;
    if (gesicherterFormularZustand && gesicherterFormularZustand.formularId === aktuellesFormularId) {
      if ("trigger_entity_id" in gesicherterFormularZustand.werte) {
        entityWert = gesicherterFormularZustand.werte.trigger_entity_id || "";
      }
      if ("trigger_from_state" in gesicherterFormularZustand.werte) {
        fromStateWert = gesicherterFormularZustand.werte.trigger_from_state || "";
      }
      if ("trigger_state" in gesicherterFormularZustand.werte) {
        stateWert = gesicherterFormularZustand.werte.trigger_state || "";
      }
    }

    const HaSelector = customElements.get("ha-selector");
    if (!HaSelector) {
      entitySlot.innerHTML = `
        <label>Auslösende Entität (Entity-ID)
          <input type="text" data-feld-name="trigger_entity_id" placeholder="z. B. binary_sensor.tuer_garage" value="${this._escape(entityWert)}" />
        </label>`;
      fromStateSlot.innerHTML = `
        <label>Ausgangszustand ("von")
          <input type="text" data-feld-name="trigger_from_state" placeholder="z. B. off" value="${this._escape(fromStateWert)}" />
        </label>`;
      stateSlot.innerHTML = `
        <label>Ziel-Zustand ("zu")
          <input type="text" data-feld-name="trigger_state" placeholder="z. B. on" value="${this._escape(stateWert)}" />
        </label>`;
      return;
    }

    const entitySelector = document.createElement("ha-selector");
    entitySelector.hass = this._hass;
    entitySelector.label = "Auslösende Entität";
    entitySelector.selector = { entity: {} };
    entitySelector.value = entityWert || undefined;
    // WICHTIG: explizit als NICHT erforderlich markieren. Ohne diese
    // Angabe kann ha-selector das Feld intern als "required" behandeln -
    // required-Felder zeigen üblicherweise KEIN Lösch-Icon an, obwohl der
    // Trigger hier ausdrücklich optional ist.
    entitySelector.required = false;
    entitySelector.dataset.feldName = "trigger_entity_id";
    entitySelector.addEventListener("value-changed", (ev) => {
      ev.stopPropagation();
      // WICHTIG: ha-selector ist eine "controlled component" - sie hält
      // den ausgewählten Wert NICHT selbst fest, sondern überlässt das
      // bewusst dem Aufrufer (üblich bei allen HA-Formular-Selectoren).
      // Ohne dieses explizite Zurückschreiben auf .value würde die
      // Auswahl beim nächsten Render (siehe unten) wieder verloren gehen.
      entitySelector.value = ev.detail.value;
      // Neu rendern, damit die Zustands-Selectoren direkt im Anschluss
      // mit der NEU gewählten Entität aufgebaut werden und deren
      // bekannte Zustände vorschlagen (genau wie im Automationen-
      // Editor). Bereits eingegebene Formularwerte bleiben durch
      // _sichereFormularZustand()/_stelleFormularZustandWieder() erhalten.
      this._render();
    });

    const fromStateSelector = document.createElement("ha-selector");
    fromStateSelector.hass = this._hass;
    fromStateSelector.label = 'Ausgangszustand ("von")';
    fromStateSelector.selector = { state: { entity_id: entityWert || undefined } };
    fromStateSelector.value = fromStateWert || undefined;
    fromStateSelector.required = false;
    fromStateSelector.dataset.feldName = "trigger_from_state";
    fromStateSelector.addEventListener("value-changed", (ev) => {
      ev.stopPropagation();
      fromStateSelector.value = ev.detail.value;
    });

    const stateSelector = document.createElement("ha-selector");
    stateSelector.hass = this._hass;
    stateSelector.label = 'Ziel-Zustand ("zu")';
    stateSelector.selector = { state: { entity_id: entityWert || undefined } };
    stateSelector.value = stateWert || undefined;
    stateSelector.required = false;
    stateSelector.dataset.feldName = "trigger_state";
    stateSelector.addEventListener("value-changed", (ev) => {
      ev.stopPropagation();
      // Aus demselben Grund wie beim Entity-Selector: den gewählten Wert
      // explizit übernehmen. Hier reicht das (ohne Neu-Rendern), da
      // beim Absenden direkt aus dem Element gelesen wird (siehe
      // _vorlagenFormularAbsenden) und kein zweiter Selector davon abhängt.
      stateSelector.value = ev.detail.value;
    });

    entitySlot.innerHTML = "";
    entitySlot.appendChild(entitySelector);
    fromStateSlot.innerHTML = "";
    fromStateSlot.appendChild(fromStateSelector);
    stateSlot.innerHTML = "";
    stateSlot.appendChild(stateSelector);

    // Zusätzlich zu einem eventuellen eingebauten Lösch-Icon der
    // Selectoren: ein eigener, garantiert sichtbarer Button, der ALLE
    // DREI Trigger-Zustandsfelder auf einen Klick leert (Über/Unter
    // bleiben davon unberührt, da sie unabhängig nutzbar sind - dafür
    // gibt es keinen eigenen Entfernen-Button, ein leeres Zahlenfeld
    // ist selbsterklärend "nicht gesetzt"). So ist das Entfernen nicht
    // von einer UI-Eigenheit des ha-selector abhängig, die sich zwischen
    // Home-Assistant-Versionen unterscheiden kann.
    if (entityWert || fromStateWert || stateWert) {
      const entfernenBtn = document.createElement("button");
      entfernenBtn.type = "button";
      entfernenBtn.className = "btn-secondary trigger-entfernen-btn";
      entfernenBtn.textContent = "Trigger entfernen";
      entfernenBtn.addEventListener("click", () => {
        entitySelector.value = undefined;
        fromStateSelector.value = undefined;
        stateSelector.value = undefined;
        this._render();
      });
      stateSlot.appendChild(entfernenBtn);
    }
  }

  _eventListenerRegistrieren(istAdmin, benutzerSensoren) {
    const eigeneUserId = this._hass.user ? this._hass.user.id : null;

    const zeitplanTypSelect = this.shadowRoot.querySelector('select[name="schedule_type_ui"]');
    if (zeitplanTypSelect) {
      zeitplanTypSelect.addEventListener("change", () => this._vorlagenZeitplanUiAktualisieren());
    }

    const menuBtn = this.shadowRoot.getElementById("menu-btn");
    if (menuBtn) {
      menuBtn.addEventListener("click", () => {
        // Feuert dasselbe HA-Event, über das auch Music Assistant und
        // Beatify die Seitenleiste ein-/ausblenden.
        this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
      });
    }

    this.shadowRoot.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        this._aktiverTab = ev.target.getAttribute("data-tab-id");
        this._render();
      });
    });

    this.shadowRoot.querySelectorAll(".eigene-erledigen").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        this._aufgabeErledigen(ev.target.getAttribute("data-task-id"), eigeneUserId);
      });
    });

    this.shadowRoot.querySelectorAll(".rang-name-klickbar").forEach((el) => {
      el.addEventListener("click", () => {
        const userId = el.getAttribute("data-user-id");
        this._aufgeklappterVerlaufUserId = this._aufgeklappterVerlaufUserId === userId ? null : userId;
        this._render();
      });
    });

    this.shadowRoot.querySelectorAll(".konto-badge-klickbar").forEach((el) => {
      el.addEventListener("click", () => {
        const userId = el.getAttribute("data-user-id");
        this._aufgeklappterPunktekontoUserId = this._aufgeklappterPunktekontoUserId === userId ? null : userId;
        this._render();
      });
    });

    this.shadowRoot.querySelectorAll(".rang-menu-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const userId = ev.target.getAttribute("data-user-id");
        this._offenesRangMenuUserId = this._offenesRangMenuUserId === userId ? null : userId;
        this._render();
      });
    });

    this.shadowRoot.querySelectorAll(".praemie-einloesen-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        const rewardName = ev.target.getAttribute("data-reward-name");
        if (confirm(`"${rewardName}" wirklich anfragen? Ein Administrator muss die Einlösung noch bestätigen.`)) {
          this._praemieAnfragen(ev.target.getAttribute("data-reward-id"), eigeneUserId);
        }
      });
    });

    if (!istAdmin) return;

    this.shadowRoot.querySelectorAll(".reset-punkte-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        const userId = ev.target.getAttribute("data-user-id");
        const userName = ev.target.getAttribute("data-user-name");
        if (confirm(`Punktestand von "${userName}" wirklich auf 0 zurücksetzen? Der Erledigungs-Verlauf wird dabei ebenfalls gelöscht.`)) {
          this._punktestandZuruecksetzen(userId);
        }
      });
    });

    this.shadowRoot.querySelectorAll(".freigeben-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        this._aufgabeFreigeben(ev.target.getAttribute("data-task-id"));
      });
    });

    this.shadowRoot.querySelectorAll(".ablehnen-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        if (confirm("Diese Erledigung wirklich ablehnen? Die Aufgabe wird wieder offen.")) {
          this._aufgabeAblehnen(ev.target.getAttribute("data-task-id"));
        }
      });
    });

    this.shadowRoot.querySelectorAll(".rueckgaengig-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        const taskName = ev.target.getAttribute("data-task-name");
        if (confirm(`Erledigung von "${taskName}" wirklich zurücknehmen? Die Punkte werden wieder abgezogen.`)) {
          this._erledigungRueckgaengig(ev.target.getAttribute("data-completion-id"));
        }
      });
    });

    const siegerehrungBtn = this.shadowRoot.querySelector(".siegerehrung-btn");
    if (siegerehrungBtn) {
      siegerehrungBtn.addEventListener("click", () => {
        // Aktuellen Höchststand direkt aus den bereits vorhandenen
        // Sensor-Daten ermitteln, um den/die Gewinner VOR der
        // Bestätigung anzuzeigen (kein zusätzlicher Service-Aufruf nötig).
        let hoechststand = 0;
        const fuehrende = [];
        benutzerSensoren.forEach((b) => {
          const punkte = Number(b.zustand.state) || 0;
          if (punkte > hoechststand) {
            hoechststand = punkte;
            fuehrende.length = 0;
            fuehrende.push(b);
          } else if (punkte === hoechststand && punkte > 0) {
            fuehrende.push(b);
          }
        });
        const namen = fuehrende
          .map((b) => this._escape(b.zustand.attributes.friendly_name || b.entityId))
          .join(", ");
        const hinweis =
          fuehrende.length > 0
            ? `Aktueller Stand: ${namen} mit ${hoechststand} Punkten.\n\n`
            : "Aktuell haben alle 0 Punkte - niemand würde gewinnen.\n\n";
        if (
          confirm(
            `${hinweis}Siegerehrung wirklich durchführen? Der/die Gewinner bekommen +1 Sieg, danach werden ALLE Punktestände auf 0 zurückgesetzt.`
          )
        ) {
          this._siegerehrungDurchfuehren();
        }
      });
    }

    this.shadowRoot.querySelectorAll(".reset-siege-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        const userId = ev.target.getAttribute("data-user-id");
        const userName = ev.target.getAttribute("data-user-name");
        if (confirm(`Sieg-Zähler von "${userName}" wirklich auf 0 zurücksetzen?`)) {
          this._siegeZuruecksetzen(userId);
        }
      });
    });

    this.shadowRoot.querySelectorAll(".punkte-abziehen-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        const userId = ev.target.getAttribute("data-user-id");
        const userName = ev.target.getAttribute("data-user-name");

        const eingabe = prompt(`Wie viele Punkte sollen "${userName}" abgezogen werden?`);
        if (eingabe === null) return; // Abgebrochen

        const amount = Number(eingabe);
        if (!Number.isFinite(amount) || amount <= 0) {
          alert("Bitte eine positive Zahl eingeben.");
          return;
        }

        const reason = prompt(`Grund für den Abzug (optional):`) || "";

        if (confirm(`"${userName}" wirklich ${amount} Punkte abziehen${reason ? ` (Grund: "${reason}")` : ""}?`)) {
          this._punkteAbziehen(userId, amount, reason);
        }
      });
    });

    this.shadowRoot.querySelectorAll(".freigeben-praemie-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        this._einloesungFreigeben(ev.target.getAttribute("data-redemption-id"));
      });
    });

    this.shadowRoot.querySelectorAll(".ablehnen-praemie-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        if (confirm("Diese Einlösung wirklich ablehnen?")) {
          this._einloesungAblehnen(ev.target.getAttribute("data-redemption-id"));
        }
      });
    });

    const toggleBtn = this.shadowRoot.getElementById("toggle-formular");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        this._formularOffen = !this._formularOffen;
        // Der Umschalt-Button öffnet immer eine LEERE "Neue Aufgabe" -
        // ein evtl. aktiver Bearbeitungs-Modus wird dabei verlassen.
        // Aufgaben-, Vorlagen- und Prämien-Formular schließen sich
        // gegenseitig aus.
        this._bearbeiteTaskId = null;
        this._vorlagenFormularOffen = false;
        this._bearbeiteVorlageId = null;
        this._praemienFormularOffen = false;
        this._bearbeitePraemieId = null;
        this._render();
      });
    }

    const toggleVorlagenBtn = this.shadowRoot.getElementById("toggle-vorlagen-formular");
    if (toggleVorlagenBtn) {
      toggleVorlagenBtn.addEventListener("click", () => {
        this._vorlagenFormularOffen = !this._vorlagenFormularOffen;
        this._bearbeiteVorlageId = null;
        this._formularOffen = false;
        this._bearbeiteTaskId = null;
        this._praemienFormularOffen = false;
        this._bearbeitePraemieId = null;
        this._render();
      });
    }

    const togglePraemienBtn = this.shadowRoot.getElementById("toggle-praemien-formular");
    if (togglePraemienBtn) {
      togglePraemienBtn.addEventListener("click", () => {
        this._praemienFormularOffen = !this._praemienFormularOffen;
        this._bearbeitePraemieId = null;
        this._formularOffen = false;
        this._bearbeiteTaskId = null;
        this._vorlagenFormularOffen = false;
        this._bearbeiteVorlageId = null;
        this._render();
      });
    }

    this.shadowRoot.querySelectorAll(".praemie-bearbeiten-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        this._bearbeitePraemieId = ev.target.getAttribute("data-reward-id");
        this._praemienFormularOffen = true;
        this._formularOffen = false;
        this._bearbeiteTaskId = null;
        this._vorlagenFormularOffen = false;
        this._bearbeiteVorlageId = null;
        this._render();
      });
    });

    this.shadowRoot.querySelectorAll(".praemie-loeschen-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        if (confirm("Diese Prämie wirklich löschen? Bereits erfolgte Einlösungen bleiben in der Historie erhalten.")) {
          this._praemieLoeschen(ev.target.getAttribute("data-reward-id"));
        }
      });
    });

    const praemieAbbrechenBtn = this.shadowRoot.getElementById("praemie-bearbeiten-abbrechen");
    if (praemieAbbrechenBtn) {
      praemieAbbrechenBtn.addEventListener("click", () => {
        this._praemienFormularOffen = false;
        this._bearbeitePraemieId = null;
        this._render();
      });
    }

    const praemieTypAuswahl = this.shadowRoot.getElementById("praemie-typ-auswahl");
    if (praemieTypAuswahl) {
      praemieTypAuswahl.addEventListener("change", (ev) => {
        const internetZeitFelder = this.shadowRoot.querySelector(".internet-zeit-felder");
        if (internetZeitFelder) {
          internetZeitFelder.style.display = ev.target.value === "internet_time" ? "" : "none";
        }
      });
    }

    const formular = this.shadowRoot.querySelector(".formular-mit-zustand");
    if (formular && (formular.id === "neue-vorlage-formular" || formular.id === "vorlage-bearbeiten-formular")) {
      formular.addEventListener("submit", (ev) => this._vorlagenFormularAbsenden(ev, formular));
    } else if (formular && (formular.id === "neue-praemie-formular" || formular.id === "praemie-bearbeiten-formular")) {
      formular.addEventListener("submit", (ev) => this._praemienFormularAbsenden(ev, formular));
    } else if (formular) {
      formular.addEventListener("submit", (ev) => {
        ev.preventDefault();
        const daten = new FormData(formular);
        const ausgewaehlteBenutzer = Array.from(
          formular.querySelectorAll('input[name="assigned_to"]:checked')
        ).map((cb) => cb.value);
        const dueInDays = daten.get("due_in_days") || "";
        const reminderDays = daten.get("reminder_days") || "";

        const formData = {
          name: daten.get("name"),
          description: daten.get("description") || "",
          score: Number(daten.get("score")),
          assigned_to: ausgewaehlteBenutzer,
        };

        if (this._bearbeiteTaskId) {
          // Beim Bearbeiten immer mitsenden - ein leerer Wert entfernt
          // die jeweilige Bedingung bewusst (siehe async_update_task).
          formData.due_in_days = dueInDays;
          formData.reminder_days = reminderDays;
          this._aufgabeAktualisieren(this._bearbeiteTaskId, formData);
        } else {
          // Beim Neuanlegen nur mitsenden, wenn tatsächlich ausgefüllt.
          if (dueInDays) formData.due_in_days = dueInDays;
          if (reminderDays) formData.reminder_days = reminderDays;
          this._neueAufgabeAnlegen(formData);
        }

        this._formularOffen = false;
        this._bearbeiteTaskId = null;
        this._render();
      });
    }

    const abbrechenBtn = this.shadowRoot.getElementById("bearbeiten-abbrechen");
    if (abbrechenBtn) {
      abbrechenBtn.addEventListener("click", () => {
        this._formularOffen = false;
        this._bearbeiteTaskId = null;
        this._render();
      });
    }

    const vorlageAbbrechenBtn = this.shadowRoot.getElementById("vorlage-bearbeiten-abbrechen");
    if (vorlageAbbrechenBtn) {
      vorlageAbbrechenBtn.addEventListener("click", () => {
        this._vorlagenFormularOffen = false;
        this._bearbeiteVorlageId = null;
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

    this.shadowRoot.querySelectorAll(".bearbeiten-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        this._bearbeiteTaskId = ev.target.getAttribute("data-task-id");
        this._formularOffen = true;
        this._vorlagenFormularOffen = false;
        this._bearbeiteVorlageId = null;
        this._praemienFormularOffen = false;
        this._bearbeitePraemieId = null;
        this._render();
      });
    });

    this.shadowRoot.querySelectorAll(".vorlage-bearbeiten-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        this._bearbeiteVorlageId = ev.target.getAttribute("data-template-id");
        this._vorlagenFormularOffen = true;
        this._formularOffen = false;
        this._bearbeiteTaskId = null;
        this._praemienFormularOffen = false;
        this._bearbeitePraemieId = null;
        this._render();
      });
    });

    this.shadowRoot.querySelectorAll(".vorlage-loeschen-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        if (confirm("Diese Standardaufgabe wirklich löschen? Bereits daraus erzeugte Aufgaben bleiben bestehen.")) {
          this._vorlageLoeschen(ev.target.getAttribute("data-template-id"));
        }
      });
    });

    this.shadowRoot.querySelectorAll(".vorlage-anlegen-btn").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        this._aufgabeAusVorlageAnlegen(ev.target.getAttribute("data-template-id"));
      });
    });
  }

  /**
   * Blendet die Zeitplan-Unterfelder (Intervall-Zeile / Wochentag-Zeile)
   * je nach aktueller Auswahl im "schedule_type_ui"-Dropdown ein oder
   * aus und passt das Einheiten-Label ("Tage"/"Wochen") an. Wird sowohl
   * beim "change"-Event des Dropdowns als auch einmalig nach jedem
   * _render() aufgerufen (damit die Sichtbarkeit auch nach einem durch
   * hass-Update ausgelösten Neuaufbau des Formulars korrekt ist).
   */
  _vorlagenZeitplanUiAktualisieren() {
    const typSelect = this.shadowRoot.querySelector('select[name="schedule_type_ui"]');
    if (!typSelect) return;
    const formular = typSelect.closest("form");
    if (!formular) return;

    const wert = typSelect.value;
    const intervallZeile = formular.querySelector('[data-zeitplan-zeile="interval"]');
    const wochentagZeile = formular.querySelector('[data-zeitplan-zeile="weekday"]');
    const einheitLabel = formular.querySelector(".zeitplan-einheit-label");

    if (intervallZeile) {
      intervallZeile.style.display = wert === "days" || wert === "weekly_interval" ? "" : "none";
    }
    if (wochentagZeile) {
      wochentagZeile.style.display = wert === "weekly_single" || wert === "weekly_interval" ? "" : "none";
    }
    if (einheitLabel) {
      einheitLabel.textContent = wert === "weekly_interval" ? "Wochen" : "Tage";
    }
  }

  /** Verarbeitet das Absenden des Standardaufgaben-Formulars (Anlegen ODER Bearbeiten). */
  _vorlagenFormularAbsenden(ev, formular) {
    ev.preventDefault();
    const daten = new FormData(formular);
    const ausgewaehlteBenutzer = Array.from(formular.querySelectorAll('input[name="assigned_to"]:checked')).map(
      (cb) => cb.value
    );
    const multiscoringFeld = formular.querySelector('input[name="multiscoring"]');
    const entityFeld = formular.querySelector('[data-feld-name="trigger_entity_id"]');
    const fromStateFeld = formular.querySelector('[data-feld-name="trigger_from_state"]');
    const stateFeld = formular.querySelector('[data-feld-name="trigger_state"]');
    const triggerEntityId = entityFeld ? entityFeld.value || "" : "";
    const triggerFromState = fromStateFeld ? fromStateFeld.value || "" : "";
    const triggerState = stateFeld ? stateFeld.value || "" : "";
    // trigger_above/trigger_below sind normale, benannte <input>-Felder
    // (kein ha-selector) - roher String-Wert aus FormData, damit sich
    // "" (leer/entfernt) von "0" (gültiger Zahlenwert 0) unterscheiden
    // lässt; die Umwandlung in eine Zahl übernimmt die Service-Schema-
    // Validierung serverseitig.
    const triggerAbove = daten.get("trigger_above") || "";
    const triggerBelow = daten.get("trigger_below") || "";
    const dueInDays = daten.get("due_in_days") || "";
    const reminderDays = daten.get("reminder_days") || "";

    // Zeitplan: die UI-Auswahl (schedule_type_ui, 4 Optionen) auf die
    // beiden tatsächlichen Backend-Felder abbilden - siehe Kommentar bei
    // der Vorbelegung in _renderVorlagenBereich().
    const zeitplanTypUiFeld = formular.querySelector('select[name="schedule_type_ui"]');
    const zeitplanIntervallFeld = formular.querySelector('input[name="schedule_interval"]');
    const zeitplanWochentagFeld = formular.querySelector('select[name="schedule_weekday"]');
    const zeitplanTypUi = zeitplanTypUiFeld ? zeitplanTypUiFeld.value : "";

    let scheduleType = "";
    let scheduleInterval = null;
    let scheduleWeekday = null;
    if (zeitplanTypUi === "days") {
      scheduleType = "days";
      scheduleInterval = Math.max(1, Number(zeitplanIntervallFeld ? zeitplanIntervallFeld.value : 1) || 1);
    } else if (zeitplanTypUi === "weekly_single") {
      scheduleType = "weekly";
      scheduleInterval = 1;
      scheduleWeekday = Number(zeitplanWochentagFeld ? zeitplanWochentagFeld.value : 0);
    } else if (zeitplanTypUi === "weekly_interval") {
      scheduleType = "weekly";
      scheduleInterval = Math.max(1, Number(zeitplanIntervallFeld ? zeitplanIntervallFeld.value : 1) || 1);
      scheduleWeekday = Number(zeitplanWochentagFeld ? zeitplanWochentagFeld.value : 0);
    }

    const formData = {
      name: daten.get("name"),
      description: daten.get("description") || "",
      score: Number(daten.get("score")),
      assigned_to: ausgewaehlteBenutzer,
      multiscoring: !!(multiscoringFeld && multiscoringFeld.checked),
    };

    if (this._bearbeiteVorlageId) {
      // Beim Bearbeiten IMMER mitsenden - ein leerer Wert entfernt den
      // jeweiligen Trigger dabei bewusst (siehe async_update_template).
      formData.trigger_entity_id = triggerEntityId;
      formData.trigger_from_state = triggerFromState;
      formData.trigger_state = triggerState;
      formData.trigger_above = triggerAbove;
      formData.trigger_below = triggerBelow;
      formData.schedule_type = scheduleType;
      if (scheduleType) formData.schedule_interval = scheduleInterval;
      if (scheduleWeekday !== null) formData.schedule_weekday = scheduleWeekday;
      formData.due_in_days = dueInDays;
      formData.reminder_days = reminderDays;
      this._vorlageAktualisieren(this._bearbeiteVorlageId, formData);
    } else {
      // Beim Neuanlegen nur mitsenden, wenn tatsächlich ausgefüllt - ein
      // leerer String ist kein gültiger Zeitplan-Typ/Zahlenwert und
      // würde die Service-Validierung von add_template fehlschlagen
      // lassen (dort ist "leer/entfernt" als Konzept nicht vorgesehen -
      // es gibt ja noch nichts zu entfernen).
      if (triggerEntityId) formData.trigger_entity_id = triggerEntityId;
      if (triggerFromState) formData.trigger_from_state = triggerFromState;
      if (triggerState) formData.trigger_state = triggerState;
      if (triggerAbove) formData.trigger_above = triggerAbove;
      if (triggerBelow) formData.trigger_below = triggerBelow;
      if (dueInDays) formData.due_in_days = dueInDays;
      if (reminderDays) formData.reminder_days = reminderDays;
      if (scheduleType) {
        formData.schedule_type = scheduleType;
        formData.schedule_interval = scheduleInterval;
        if (scheduleWeekday !== null) formData.schedule_weekday = scheduleWeekday;
      }
      this._vorlageAnlegen(formData);
    }

    this._vorlagenFormularOffen = false;
    this._bearbeiteVorlageId = null;
    this._render();
  }

  /** Verarbeitet das Absenden des Prämien-Formulars (Anlegen ODER Bearbeiten). */
  _praemienFormularAbsenden(ev, formular) {
    ev.preventDefault();
    const daten = new FormData(formular);
    const rewardType = daten.get("reward_type") || "generic";

    const formData = {
      name: daten.get("name"),
      description: daten.get("description") || "",
      cost: Number(daten.get("cost")),
      reward_type: rewardType,
    };

    if (rewardType === "internet_time") {
      const switchEntityId = daten.get("switch_entity_id") || "";
      // WICHTIG: Beim Neuanlegen verlangt das Service-Schema entweder
      // eine gültige Entity-ID oder GAR KEIN Feld (kein leerer String
      // erlaubt) - beim Bearbeiten ist ein leerer String dagegen
      // bewusst als "Entität entfernen" zugelassen. Daher hier je nach
      // Modus unterschiedlich behandeln.
      if (switchEntityId || this._bearbeitePraemieId) {
        formData.switch_entity_id = switchEntityId;
      }
      formData.duration_minutes = Number(daten.get("duration_minutes")) || 30;
    }
    // Beim Wechsel WEG von "internet_time" werden switch_entity_id/
    // duration_minutes bewusst NICHT mitgesendet (weder Wert noch
    // "null" - Letzteres würde an der Service-Schema-Validierung
    // scheitern, vol.Coerce(int) akzeptiert kein None). Sie bleiben im
    // Backend als ungenutzte Alt-Werte stehen, was unkritisch ist, da
    // ausschließlich reward_type das tatsächliche Verhalten bestimmt.

    if (this._bearbeitePraemieId) {
      this._praemieAktualisieren(this._bearbeitePraemieId, formData);
    } else {
      this._praemieAnlegen(formData);
    }

    this._praemienFormularOffen = false;
    this._bearbeitePraemieId = null;
    this._render();
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
      .kopf {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .kopf h1 {
        font-size: 1.6em;
        color: var(--primary-text-color);
        margin: 0 0 20px 0;
      }
      .menu-btn {
        background: none;
        border: none;
        cursor: pointer;
        font-size: 1.3em;
        color: var(--primary-text-color);
        padding: 4px 8px 24px 0;
        line-height: 1;
        flex-shrink: 0;
        opacity: 0.8;
      }
      .menu-btn:hover {
        opacity: 1;
      }
      .tab-leiste {
        display: flex;
        gap: 6px;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        padding-bottom: 8px;
        margin-bottom: 24px;
        border-bottom: 1px solid var(--divider-color, #eee);
      }
      .tab-btn {
        flex-shrink: 0;
        background: none;
        border: none;
        border-bottom: 3px solid transparent;
        border-radius: 0;
        padding: 8px 12px;
        font-size: 0.95em;
        font-weight: 500;
        color: var(--secondary-text-color);
        cursor: pointer;
        white-space: nowrap;
      }
      .tab-btn-aktiv {
        color: var(--primary-color);
        border-bottom-color: var(--primary-color);
        font-weight: 700;
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
        /* WICHTIG: kein overflow:hidden mehr - würde das absolut
           positionierte ⋮-Aktionsmenü (siehe .rang-aktionen-popup)
           an den Rändern der Liste abschneiden, v. a. bei der letzten
           Zeile. Der kleine kosmetische Nachteil (eckige statt
           abgerundete Ecken bei einer eingefärbten "ich"-Zeile ganz
           oben/unten) wiegt das nicht auf.
        */
      }
      .rang-eintrag {
        position: relative;
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        flex-wrap: wrap;
        gap: 10px;
        padding: 12px 16px;
        border-bottom: 1px solid var(--divider-color, #eee);
        color: var(--primary-text-color);
      }
      .rang-eintrag:last-child { border-bottom: none; }
      .rang-eintrag:first-child { border-radius: 12px 12px 0 0; }
      .rang-eintrag:last-child { border-radius: 0 0 12px 12px; }
      .rang-eintrag:only-child { border-radius: 12px; }
      .rang-eintrag.ich { background: rgba(var(--rgb-primary-color, 3,169,244), 0.08); font-weight: 600; }
      .rang-rechts {
        display: flex;
        align-items: center;
        gap: 10px;
      }
      .rang-badges {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        flex-wrap: wrap;
        gap: 10px;
      }
      .rang-menu-wrapper {
        flex-shrink: 0;
      }
      .rang-menu-btn {
        background: none;
        border: none;
        cursor: pointer;
        font-size: 1.1em;
        line-height: 1;
        padding: 2px 6px;
        color: var(--secondary-text-color);
      }
      .rang-menu-btn:hover {
        color: var(--primary-text-color);
      }
      .rang-aktionen-popup {
        /* WICHTIG: bewusst relativ zur GESAMTEN Zeile (.rang-eintrag,
           siehe position:relative oben) positioniert statt relativ zum
           winzigen ⋮-Button-Wrapper - Letzteres führte in Kombination
           mit dem umbrechenden Flex-Layout der Badges (flex-wrap) dazu,
           dass das Popup weit links am Bildschirmrand statt beim Button
           erschien. Die Zeile selbst hat eine stabile, volle Breite und
           liefert damit einen zuverlässigen Bezugsrahmen.
        */
        position: absolute;
        top: 100%;
        right: 16px;
        z-index: 10;
        display: flex;
        flex-direction: column;
        gap: 6px;
        min-width: 170px;
        margin-top: 4px;
        padding: 8px;
        background: var(--card-background-color);
        border: 1px solid var(--divider-color, #ccc);
        border-radius: 8px;
        box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,0.25));
      }
      .rang-aktionen-popup button {
        width: 100%;
      }
      .rang-punkte { color: var(--primary-color); font-weight: 700; }
      .reset-punkte-btn,
      .reset-siege-btn {
        font-size: 0.8em;
        padding: 4px 10px;
      }
      .sieg-badge,
      .konto-badge {
        font-size: 0.85em;
        white-space: nowrap;
      }
      .konto-badge-klickbar {
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        user-select: none;
      }
      .konto-verlauf-guthaben {
        font-weight: 600;
        padding: 6px 0 10px;
        color: var(--primary-text-color);
      }
      .punkte-badge-abgang {
        background: rgba(var(--rgb-danger-color, 244,67,54), 0.12);
        color: var(--error-color, #f44336);
      }
      .abschnitt-kopf-mit-aktion {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 32px;
        margin-bottom: 12px;
      }
      .rangliste-titel { margin: 0; }
      .internet-zeit-felder {
        display: flex;
        flex-direction: column;
        gap: 12px;
        border: 1px solid var(--divider-color, #ccc);
        border-radius: 6px;
        padding: 10px 12px;
      }
      .rang-name-klickbar {
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 6px;
        user-select: none;
      }
      .verlauf-pfeil {
        font-size: 0.7em;
        color: var(--secondary-text-color);
      }
      .verlauf-bereich {
        background: var(--secondary-background-color, rgba(0,0,0,0.03));
        padding: 8px 16px;
        border-bottom: 1px solid var(--divider-color, #eee);
      }
      .verlauf-eintrag {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 0;
        border-bottom: 1px solid var(--divider-color, #eee);
        font-size: 0.9em;
      }
      .verlauf-eintrag:last-child { border-bottom: none; }
      .verlauf-info {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      .verlauf-name { color: var(--primary-text-color); }
      .verlauf-datum { font-size: 0.85em; color: var(--secondary-text-color); }
      .verlauf-aktion {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .aufgaben-karte.wartend { opacity: 0.75; }
      .punkte-badge-wartend {
        background: var(--secondary-background-color, rgba(0,0,0,0.08));
        color: var(--secondary-text-color);
      }

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
      .aufgaben-karte-ueberfaellig {
        border: 1px solid var(--error-color, #f44336);
        background: rgba(var(--rgb-error-color, 244,67,54), 0.06);
      }
      .faelligkeit-hinweis {
        color: var(--secondary-text-color);
        font-size: 0.8em;
        margin-top: 6px;
      }
      .faelligkeit-ueberfaellig {
        color: var(--error-color, #f44336);
        font-weight: 600;
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
      .formular-titel {
        margin: 0;
        font-size: 1.05em;
        color: var(--primary-text-color);
      }
      .zustaendigkeit-feld {
        border: 1px solid var(--divider-color, #ccc);
        border-radius: 6px;
        padding: 10px 12px 12px;
        margin: 0;
      }
      .zustaendigkeit-feld legend {
        font-size: 0.9em;
        color: var(--secondary-text-color);
        padding: 0 4px;
      }
      .benutzer-checkbox {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 2px;
        font-size: 0.95em;
        color: var(--primary-text-color);
        cursor: pointer;
      }
      .benutzer-checkbox input[type="checkbox"] {
        width: 18px;
        height: 18px;
        accent-color: var(--primary-color);
        cursor: pointer;
      }
      .hinweis-klein {
        font-size: 0.85em;
        color: var(--secondary-text-color);
      }
      .formular-aktionen {
        display: flex;
        gap: 10px;
      }
      .multiscoring-feld {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        font-size: 0.9em;
        color: var(--primary-text-color);
        cursor: pointer;
      }
      .multiscoring-feld input[type="checkbox"] {
        width: 18px;
        height: 18px;
        flex-shrink: 0;
        margin-top: 2px;
        accent-color: var(--primary-color);
        cursor: pointer;
      }
      .trigger-feld {
        border: 1px solid var(--divider-color, #ccc);
        border-radius: 6px;
        padding: 10px 12px 12px;
        margin: 0;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .trigger-feld legend {
        font-size: 0.9em;
        color: var(--secondary-text-color);
        padding: 0 4px;
      }
      .ha-selector-slot label {
        display: flex;
        flex-direction: column;
        gap: 4px;
        font-size: 0.9em;
        color: var(--secondary-text-color);
      }
      .ha-selector-slot input {
        font-family: inherit;
        font-size: 1em;
        padding: 8px;
        border-radius: 6px;
        border: 1px solid var(--divider-color, #ccc);
        background: var(--primary-background-color);
        color: var(--primary-text-color);
      }
      .trigger-entfernen-btn {
        align-self: flex-start;
        margin-top: 2px;
      }
      .zeitplan-feld {
        border: 1px solid var(--divider-color, #ccc);
        border-radius: 6px;
        padding: 10px 12px 12px;
        margin: 0;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .zeitplan-feld legend {
        font-size: 0.9em;
        color: var(--secondary-text-color);
        padding: 0 4px;
      }
      .zeitplan-feld label {
        display: flex;
        flex-direction: column;
        gap: 4px;
        font-size: 0.9em;
        color: var(--secondary-text-color);
      }
      .zeitplan-intervall-feld {
        flex-direction: row !important;
        align-items: center;
        gap: 8px !important;
      }
      .zeitplan-feld select,
      .zeitplan-feld input[type="number"] {
        font-family: inherit;
        font-size: 1em;
        padding: 8px;
        border-radius: 6px;
        border: 1px solid var(--divider-color, #ccc);
        background: var(--primary-background-color);
        color: var(--primary-text-color);
      }
      .zeitplan-intervall-feld input[type="number"] {
        width: 70px;
      }
      .vorlage-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 6px;
      }
      .vorlage-badge {
        display: inline-block;
        font-size: 0.75em;
        background: rgba(var(--rgb-primary-color, 3,169,244), 0.12);
        color: var(--primary-color);
        border-radius: 999px;
        padding: 2px 9px;
      }
    `;
  }
}

customElements.define("aufgaben-scoreboard-panel", AufgabenScoreboardPanel);
