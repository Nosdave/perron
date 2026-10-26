// Perron Studio – Home Assistant side panel (no build step, no external dependencies).
// Lists tiles, edits them with a pixel-exact preview rendered by the board, shows the board live.

const TPL = {
  hero: "Zahl", kpi: "Kennzahlen", list: "Liste", prog: "Fortschritt", msg: "Text",
  agenda: "Agenda", ring: "Klingel", img: "Bild", cv: "Frei", json: "Karten-JSON (Profi)",
};
const MODES = { manual: "Nur auf Abruf", always: "Immer", condition: "Solange Bedingung wahr", schedule: "Zeitfenster" };
const ZONES = { f: "Vollbild", p: "Kachel rechts", l: "Infozeile" };
const PRIO = { 1: "Ereignis (wichtig)", 2: "Zustand (normal)", 3: "Hintergrund" };
const ACC = { y: "#ffc400", g: "#4fd18b", b: "#41bdf5", v: "#b48cff", w: "#ffe9cc" };
const COLORS = { w: "normal", a: "Achtung (gelb)", r: "Alarm (rot)", s: "grau", g: "grün", b: "blau", y: "gelb", v: "violett" };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

class PerronStudioPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.tiles = [];
    this.external = [];      // cards that automations send to the board
    this.autos = [];         // automations that send cards (from their configuration)
    this.meta = null;
    this.edit = null;        // tile being edited (copy)
    this.zone = "f";         // preview zone
    this._liveUrl = null;
    this._prevUrl = null;
    this._thumbs = {};
  }

  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (first) this._init();
  }
  set panel(p) { this._panel = p; }
  set narrow(n) { this._narrow = n; }

  disconnectedCallback() { clearInterval(this._liveTimer); }
  connectedCallback() { if (this._hass && !this._liveTimer) this._startLive(); }

  async _init() {
    this._renderShell();
    try {
      this.meta = await this._hass.callApi("GET", "perron_studio/meta");
      this.tiles = await this._hass.callApi("GET", "perron_studio/tiles");
      await this._loadExternal();
    } catch (e) {
      this._toast("Perron Studio nicht erreichbar: " + (e.message || e));
    }
    this._renderList();
    this._startLive();
  }

  async _loadExternal() {
    const x = await this._hass.callApi("GET", "perron_studio/external");
    this.external = x.cards || [];
    this.autos = x.automations || [];
  }

  _extRow(x, id) {
    if (!x) {
      return `<tr><td></td><td><span class="chip">id ${esc(id)}</span></td><td colspan="3" class="hint">noch nicht gesehen – erscheint, sobald die Automation diese Karte schickt</td></tr>`;
    }
    return `
    <tr>
      <td><img data-xthumb="${esc(x.id)}" alt=""></td>
      <td><b>${esc((x.card || {}).ti || x.id)}</b><br><span class="chip">id ${esc(x.id)}</span><span class="chip">${esc(TPL[(x.card || {}).t] || (x.card || {}).t || "")}</span></td>
      <td>${esc((x.at || "").replace("T", " ").slice(0, 16))}<br><span class="hint">${x.count || 0}× gesendet</span></td>
      <td>${x.deleted ? '<span class="chip">gerade aus</span>' : '<span class="chip">auf der Tafel</span>'}${x.taken ? '<span class="chip">als Kachel übernommen</span>' : ""}</td>
      <td><div class="acts">${x.card ? `<button class="ghost" data-xshow="${esc(x.id)}">Zeigen</button>` : ""}
        ${x.card && !x.taken ? `<button data-ximport="${esc(x.id)}">Übernehmen</button>` : ""}</div></td>
    </tr>`;
  }

  _extSection() {
    const byId = Object.fromEntries(this.external.map((x) => [x.id, x]));
    const used = new Set();
    let h = "";
    for (const a of this.autos) {
      const ids = a.ids.length ? a.ids : [];
      ids.forEach((i) => used.add(i));
      h += `<tr><td colspan="5" style="background:var(--secondary-background-color)"><b>${esc(a.name)}</b>
        <span class="chip">${a.on ? "an" : "aus"}</span>${a.config_id ? `<a class="chip" href="/config/automation/edit/${encodeURIComponent(a.config_id)}" target="_top">in HA öffnen</a>` : ""}${a.last_triggered ? `<span class="hint">zuletzt ${esc(a.last_triggered)}</span>` : ""}</td></tr>`;
      h += ids.length ? ids.map((i) => this._extRow(byId[i], i)).join("")
        : '<tr><td></td><td colspan="4" class="hint">Karten-id per Template – erscheint beim ersten Senden</td></tr>';
    }
    const rest = this.external.filter((x) => !used.has(x.id));
    if (rest.length) {
      h += `<tr><td colspan="5" style="background:var(--secondary-background-color)"><b>Weitere gesehene Karten</b></td></tr>`;
      h += rest.map((x) => this._extRow(x, x.id)).join("");
    }
    return h;
  }

  // ------------------------------------------------------------------ helpers
  async _img(method, path, body) {
    const r = await this._hass.fetchWithAuth("/api/" + path, {
      method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) {
      let t = await r.text();
      try { t = JSON.parse(t).message || t; } catch (_) {}
      throw new Error(t);
    }
    this._night = r.headers.get("X-Perron-Night") === "1";
    return URL.createObjectURL(await r.blob());
  }
  _toast(msg) {
    const t = this.shadowRoot.getElementById("toast");
    if (!t) return;
    t.textContent = msg; t.classList.add("on");
    clearTimeout(this._tt); this._tt = setTimeout(() => t.classList.remove("on"), 3500);
  }
  _startLive() {
    clearInterval(this._liveTimer);
    const tick = async () => {
      if (document.hidden) return;
      const img = this.shadowRoot.getElementById("live");
      if (!img) return;
      try {
        const u = await this._img("GET", "perron_studio/live");
        if (this._liveUrl) URL.revokeObjectURL(this._liveUrl);
        this._liveUrl = u; img.src = u;
        this.shadowRoot.getElementById("livestate").textContent = "live";
      } catch (e) {
        this.shadowRoot.getElementById("livestate").textContent = "offline";
      }
    };
    tick();
    this._liveTimer = setInterval(tick, 2000);
  }
  _summaryWhen(t) {
    const w = t.when || {};
    const parts = [MODES[w.mode] || w.mode];
    if (w.mode === "schedule") parts.push(`${w.days || ""} ${w.from || ""}–${w.to || ""}`);
    if (+w.every > 0) parts.push(`alle ${Math.round(w.every / 60)} min für ${w.show || 10} s`);
    if ((w.events || []).length) parts.push(`${w.events.length}× Ereignis`);
    if (w.voice) parts.push(`„${w.voice}“`);
    return parts.filter(Boolean);
  }

  // ------------------------------------------------------------------ shell + list
  _renderShell() {
    this.shadowRoot.innerHTML = `
<style>
  :host{display:block;background:var(--primary-background-color);color:var(--primary-text-color);min-height:100%;font-family:var(--paper-font-body1_-_font-family,Roboto,sans-serif)}
  header{display:flex;align-items:center;gap:10px;padding:12px 20px;border-bottom:1px solid var(--divider-color);background:var(--app-header-background-color,var(--primary-background-color))}
  header h1{flex:1;font-size:20px;font-weight:400;margin:0}
  main{padding:16px 20px;display:grid;gap:16px;max-width:1300px}
  .card{background:var(--card-background-color);border-radius:var(--ha-card-border-radius,12px);border:1px solid var(--divider-color);padding:16px}
  .card h2{margin:0 0 12px;font-size:15px;font-weight:500;display:flex;gap:8px;align-items:center}
  button{font:inherit;cursor:pointer;border-radius:8px;padding:7px 14px;border:1px solid var(--primary-color);background:var(--primary-color);color:var(--text-primary-color,#fff)}
  button.ghost{background:transparent;color:var(--primary-color)}
  button.danger{background:transparent;color:var(--error-color,#db4437);border-color:var(--error-color,#db4437)}
  .led{width:100%;max-width:960px;border-radius:8px;background:#0b0b0d;image-rendering:auto;display:block}
  .live{display:grid;grid-template-columns:minmax(0,1fr) 240px;gap:16px}
  .stat div{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--divider-color);font-size:13px}
  .chip{display:inline-block;background:var(--secondary-background-color);border-radius:999px;padding:2px 10px;font-size:12px;margin:2px 4px 2px 0}
  table{width:100%;border-collapse:collapse}
  th{font-size:12px;color:var(--secondary-text-color);text-align:left;font-weight:500;padding:6px 8px;text-transform:uppercase;letter-spacing:.04em}
  td{padding:8px;border-top:1px solid var(--divider-color);vertical-align:middle}
  td img{width:150px;border-radius:4px;display:block;background:#0b0b0d}
  .acts{display:flex;gap:6px;justify-content:flex-end}
  .edit{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;align-items:start}
  .sticky{position:sticky;top:8px}
  label{display:block;font-size:12px;color:var(--secondary-text-color);margin:10px 0 4px}
  input,select,textarea{width:100%;box-sizing:border-box;font:inherit;padding:8px 10px;border-radius:8px;border:1px solid var(--divider-color);background:var(--secondary-background-color);color:var(--primary-text-color)}
  textarea{font-family:ui-monospace,Consolas,monospace;font-size:13px;min-height:60px}
  .row{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px}
  .seg{display:flex;flex-wrap:wrap;gap:6px}
  .seg span{border:1px solid var(--divider-color);border-radius:8px;padding:6px 10px;cursor:pointer;font-size:13px}
  .seg span.on{border-color:var(--primary-color);color:var(--primary-color);background:rgba(3,169,244,.1)}
  .sw span{display:inline-block;width:24px;height:24px;border-radius:50%;margin-right:6px;cursor:pointer;border:2px solid transparent}
  .sw span.on{border-color:var(--primary-text-color)}
  .sub{border:1px solid var(--divider-color);border-radius:10px;padding:8px 10px;margin-top:8px}
  .sub h3{margin:0;font-size:13px;font-weight:500}
  .hint{font-size:12px;color:var(--secondary-text-color);margin-top:6px}
  .err{color:var(--error-color,#db4437);font-size:13px;margin-top:8px;min-height:1em}
  .toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:#323232;color:#fff;padding:10px 16px;border-radius:8px;opacity:0;transition:opacity .2s;pointer-events:none}
  .toast.on{opacity:1}
  @media (max-width:900px){.live,.edit{grid-template-columns:1fr}.sticky{position:static}}
</style>
<header><h1>Perron Studio</h1><button class="ghost" id="newbtn">+ Neue Kachel</button></header>
<main id="main"></main>
<div class="toast" id="toast"></div>`;
    this.shadowRoot.getElementById("newbtn").onclick = () => this._new();
  }

  _renderList() {
    this.edit = null;
    const b = (this.meta && this.meta.board) || {};
    const main = this.shadowRoot.getElementById("main");
    main.innerHTML = `
<section class="card">
  <h2>Live – Tafel <span class="chip" id="livestate">…</span></h2>
  <div class="live">
    <img class="led" id="live" alt="Tafel live">
    <div class="stat">
      <div><span>Gerät</span><b>${esc(b.device || "–")}</b></div>
      <div><span>Adresse</span><b>${esc(b.host || "–")}</b></div>
      <div><span>Verbindung</span><b>${b.online ? "online" : "offline"}</b></div>
      <div><span>Zugriff (Token)</span><b>${b.token_ok ? "ok" : "ausstehend"}</b></div>
      <div><span>Kacheln</span><b>${this.tiles.length} · ${this.tiles.filter((t) => (t._status || {}).on).length} Automationen an</b></div>
    </div>
  </div>
</section>
<section class="card">
  <h2>Kacheln</h2>
  ${this.tiles.length ? "" : '<p class="hint">Noch keine Kacheln. Mit „+ Neue Kachel“ anlegen.</p>'}
  <table>${this.tiles.length ? "<tr><th>Vorschau</th><th>Kachel</th><th>Wann</th><th>Wo</th><th>An</th><th></th></tr>" : ""}
  ${this.tiles.map((t) => `
    <tr data-id="${esc(t.id)}">
      <td><img data-thumb="${esc(t.id)}" alt=""></td>
      <td><b>${esc(t.name)}</b><br><span class="chip">${esc(TPL[t.template] || t.template)}</span>${this._statusChips(t)}</td>
      <td>${this._summaryWhen(t).map((s) => `<span class="chip">${esc(s)}</span>`).join("")}</td>
      <td>${esc(ZONES[(t.where || {}).zone] || "")}</td>
      <td><input type="checkbox" data-en="${esc(t.id)}" ${t.enabled !== false ? "checked" : ""} style="width:auto"></td>
      <td><div class="acts"><button class="ghost" data-show="${esc(t.id)}">Zeigen</button><button data-edit="${esc(t.id)}">Bearbeiten</button></div></td>
    </tr>`).join("")}
  </table>
</section>
<section class="card">
  <h2>Karten aus Automationen <span class="chip">${this.autos.length} Automationen · ${this.external.length} Karten gesehen</span></h2>
  <p class="hint">Automationen, die Karten an die Tafel schicken – Studio liest sie mit, ändert aber nichts.
  „Zeigen“ holt die letzte Fassung jetzt auf die Tafel (auch per <code>perron_studio.show</code> mit der Karten-id).
  „Übernehmen“ legt eine Kachel „Karten-JSON“ als Startpunkt an; die Automation läuft weiter, bis du sie abschaltest.</p>
  ${this.autos.length || this.external.length ? "" : '<p class="hint">Keine gefunden.</p>'}
  <table>${this._extSection()}</table>
</section>`;
    main.querySelectorAll("[data-xshow]").forEach((el) => (el.onclick = async () => {
      try {
        await this._hass.callApi("POST", "perron_studio/external", { action: "show", id: el.dataset.xshow });
        this._toast("Auf der Tafel");
      } catch (e) { this._toast("Fehler: " + (e.message || e)); }
    }));
    main.querySelectorAll("[data-ximport]").forEach((el) => (el.onclick = async () => {
      try {
        const t = await this._hass.callApi("POST", "perron_studio/external", { action: "import", id: el.dataset.ximport });
        this.tiles = await this._hass.callApi("GET", "perron_studio/tiles");
        await this._loadExternal();
        this._open(t.id);
      } catch (e) { this._toast("Fehler: " + (e.message || e)); }
    }));
    main.querySelectorAll("[data-edit]").forEach((el) => (el.onclick = () => this._open(el.dataset.edit)));
    main.querySelectorAll("[data-show]").forEach((el) => (el.onclick = () => this._showNow(this.tiles.find((t) => t.id === el.dataset.show))));
    main.querySelectorAll("[data-en]").forEach((el) => (el.onchange = async () => {
      const t = this.tiles.find((x) => x.id === el.dataset.en);
      t.enabled = el.checked;
      await this._save(t, false);
    }));
    this._loadThumbs();
  }

  async _loadThumbs() {  // board renders one preview at a time -> sequential
    for (const t of this.tiles) {
      const img = this.shadowRoot.querySelector(`[data-thumb="${CSS.escape(t.id)}"]`);
      if (!img) return;
      try {
        const u = await this._img("POST", "perron_studio/preview", { tile: t, zone: (t.where || {}).zone || "f" });
        img.src = u;
      } catch (e) {  // e.g. a Karten-JSON tile with nothing to show right now
        const n = document.createElement("span");
        n.className = "hint";
        n.textContent = /keine Karte/.test(e.message || "") ? "gerade keine Karte" : "Tafel offline";
        img.replaceWith(n);
      }
      await new Promise((r) => setTimeout(r, 300));
    }
    for (const x of this.external) {
      const img = this.shadowRoot.querySelector(`[data-xthumb="${CSS.escape(x.id)}"]`);
      if (!img || !x.tile) continue;
      try {
        img.src = await this._img("POST", "perron_studio/preview", { tile: x.tile, zone: (x.tile.where || {}).zone || "p" });
      } catch (_) { /* board offline */ }
      await new Promise((r) => setTimeout(r, 300));
    }
  }

  async _new() {
    const t = await this._hass.callApi("POST", "perron_studio/tiles", { new: true, name: "Neue Kachel" });
    this.tiles.push(t);
    this._open(t.id);
  }

  _statusChips(t) {
    const st = t._status || {};
    if (!st.saved) return '<span class="chip">Entwurf – noch keine Automation</span>';
    if (t._rebuilt) return '<span class="chip" style="color:var(--warning-color,#e8a33c)">aus der Automation wiederhergestellt – bitte prüfen und einmal speichern</span>'
      + `<a class="chip" href="/config/automation/edit/${encodeURIComponent(st.config_id)}" target="_top">in HA öffnen</a>`;
    return `<span class="chip">Automation ${st.on ? "an" : "aus"}</span>`
      + (st.modified ? '<span class="chip" style="color:var(--error-color)">in HA geändert</span>' : "")
      + `<a class="chip" href="/config/automation/edit/${encodeURIComponent(st.config_id)}" target="_top">in HA öffnen</a>`;
  }

  async _save(tile, back = true) {
    const old = this.tiles.find((t) => t.id === tile.id);
    if (old && (old._status || {}).modified && !confirm("Die Automation dieser Kachel wurde in Home Assistant von Hand geändert. Speichern überschreibt diese Änderungen. Fortfahren?")) return false;
    try {
      const saved = await this._hass.callApi("POST", "perron_studio/tiles", { tile });
      const i = this.tiles.findIndex((t) => t.id === saved.id);
      if (i >= 0) this.tiles[i] = saved; else this.tiles.push(saved);
      this._toast("Gespeichert – als Automation „Perron Studio: " + saved.name + "“");
      this.tiles = await this._hass.callApi("GET", "perron_studio/tiles");
      if (back) this._renderList();
      return true;
    } catch (e) { this._toast("Fehler: " + (e.message || e)); return false; }
  }

  async _showNow(tile) {
    if (!((this.tiles.find((t) => t.id === tile.id) || {})._status || {}).saved) {
      this._toast("Erst speichern – gezeigt wird über die Automation der Kachel");
      return;
    }
    try {
      await this._hass.callApi("POST", "perron_studio/show", { tile, zone: (tile.where || {}).zone, duration: (tile.where || {}).duration });
      this._toast("Auf der Tafel");
    } catch (e) { this._toast("Fehler: " + (e.message || e)); }
  }

  // ------------------------------------------------------------------ editor
  _open(id) {
    this.edit = JSON.parse(JSON.stringify(this.tiles.find((t) => t.id === id)));
    this.zone = (this.edit.where || {}).zone || "f";
    this._renderEditor();
  }

  _field(label, key, ph = "", obj = this.edit) {
    return `<label>${esc(label)}</label><input data-k="${esc(key)}" value="${esc(obj[key] ?? "")}" placeholder="${esc(ph)}" list="ents">`;
  }

  _iconSelect(path, val) {
    const icons = (this.meta && this.meta.icons) || [];
    return `<select data-p="${esc(path)}"><option value="">– kein Symbol –</option>${icons.map((i) => `<option ${i === val ? "selected" : ""}>${esc(i)}</option>`).join("")}</select>`;
  }
  _colorSelect(path, val) {
    return `<select data-p="${esc(path)}">${Object.entries(COLORS).map(([k, v]) => `<option value="${k}" ${k === (val || "w") ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>`;
  }

  _contentFields() {
    const t = this.edit, tpl = t.template;
    const H = "Wert, Entität (sensor.x) oder Template {{ … }}";
    let h = this._field("Titel", "title", "z. B. Energie");
    if (["hero", "prog", "ring"].includes(tpl)) {
      if (tpl !== "ring") h += `<div class="row"><div>${this._field("Wert", "value", H)}</div><div>${this._field("Einheit", "unit", "min, kW …")}</div></div>`;
      if (tpl === "prog") h += this._field("Fortschritt (%)", "pct", "{{ states('sensor.x') }}");
      h += `<div class="row"><div>${this._field(tpl === "prog" ? "Zeile links" : "Zeile 1", "sub1")}</div><div>${this._field(tpl === "prog" ? "Zeile rechts" : "Zeile 2", "sub2")}</div></div>`;
      if (tpl === "ring") h += this._field("Kamerabild (Entität)", "image", "camera.wohnungstur");
    } else if (tpl === "msg") {
      h += `<label>Text</label><textarea data-k="text">${esc(t.text || "")}</textarea>`;
    } else if (tpl === "img") {
      h += this._field("Bild: Kamera-Entität oder URL", "image", "camera.x oder http://…/bild.png");
      h += this._field("Bildzeile", "sub1");
    } else if (tpl === "json") {
      h += `<label>Karte als JSON – darf ein Template sein (Ergebnis leer oder <code>none</code> = gerade keine Karte)</label>
        <textarea data-k="card" style="min-height:260px">${esc(t.card || "{}")}</textarea>
        <p class="hint">Felder wie in docs/cards.md (t, ti, val, sub, kpi, rows, p, z, s, every, show …). <code>p: 0</code> = Alarm (Vollbild bis die Vorlage wieder leer ist).
        ${t.from_automation ? `Übernommen von der Automations-Karte <code>${esc(t.from_automation)}</code> – Werte hier durch Templates ersetzen, dann die Automation abschalten.` : ""}</p>`;
      return h;
    } else if (tpl === "cv") {
      h += `<label>Elemente (JSON, siehe docs/cards.md)</label><textarea data-k="elements">${esc(t.elements || "[]")}</textarea>`;
    } else if (tpl === "kpi") {
      t.cells = t.cells && t.cells.length ? t.cells : [{}, {}, {}];
      h += t.cells.map((c, i) => `<div class="sub"><h3>Feld ${i + 1}</h3>
        <div class="row"><div><label>Beschriftung</label><input data-p="cells.${i}.label" value="${esc(c.label || "")}"></div>
        <div><label>Wert</label><input data-p="cells.${i}.value" value="${esc(c.value || "")}" placeholder="${esc(H)}" list="ents"></div>
        <div><label>Einheit</label><input data-p="cells.${i}.unit" value="${esc(c.unit || "")}"></div></div>
        <div class="row"><div><label>Symbol</label>${this._iconSelect(`cells.${i}.icon`, c.icon)}</div>
        <div><label>Farbe</label>${this._colorSelect(`cells.${i}.color`, c.color)}</div>
        <div><label>Balken %</label><input data-p="cells.${i}.pct" value="${esc(c.pct || "")}" list="ents"></div>
        <div><label>Unterzeile</label><input data-p="cells.${i}.sub" value="${esc(c.sub || "")}"></div></div></div>`).join("");
    } else if (tpl === "list" || tpl === "agenda") {
      t.rows = t.rows || [];
      const max = tpl === "agenda" ? 8 : 4;
      h += t.rows.map((r, i) => `<div class="sub"><h3>Zeile ${i + 1} <a href="#" data-delrow="${i}" style="float:right;color:var(--error-color)">entfernen</a></h3>
        <div class="row"><div><label>Symbol</label>${this._iconSelect(`rows.${i}.icon`, r.icon)}</div>
        <div><label>Text</label><input data-p="rows.${i}.label" value="${esc(r.label || "")}" list="ents"></div>
        <div><label>${tpl === "agenda" ? "Zeit" : "Wert"}</label><input data-p="rows.${i}.value" value="${esc(r.value || "")}" list="ents"></div>
        <div><label>Farbe</label>${this._colorSelect(`rows.${i}.color`, r.color)}</div></div></div>`).join("");
      if (t.rows.length < max) h += `<p><button class="ghost" id="addrow">+ Zeile</button></p>`;
    }
    if (tpl !== "cv") {
      h += `<div class="row"><div><label>Symbol</label>${this._iconSelect("icon", t.icon)}</div><div><label>Akzentfarbe</label>
        <div class="sw">${Object.entries(ACC).map(([k, c]) => `<span data-acc="${k}" class="${(t.accent || "w") === k ? "on" : ""}" style="background:${c}"></span>`).join("")}</div></div></div>`;
    }
    return h;
  }

  _renderEditor() {
    const t = this.edit, w = t.when, wh = t.where;
    const ents = Object.keys(this._hass.states).sort();
    const main = this.shadowRoot.getElementById("main");
    main.innerHTML = `
<datalist id="ents">${ents.map((e) => `<option value="${esc(e)}">`).join("")}</datalist>
<section class="card"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
  <button class="ghost" id="back">← Zurück</button>
  <input data-k="name" value="${esc(t.name)}" style="max-width:280px;font-size:16px">
  <span style="flex:1"></span>
  <button class="danger" id="del">Löschen</button><button class="ghost" id="shownow">Jetzt zeigen</button><button id="save">Speichern</button>
</div></section>
<div class="edit">
  <section class="card">
    <h2>Inhalt</h2>
    <label>Vorlage</label>
    <div class="seg">${Object.entries(TPL).map(([k, v]) => `<span data-tpl="${k}" class="${t.template === k ? "on" : ""}">${v}</span>`).join("")}</div>
    <div id="content">${this._contentFields()}</div>
    <h2 style="margin-top:20px">Wann</h2>
    <label>Anzeigen</label>
    <select data-p="when.mode">${Object.entries(MODES).map(([k, v]) => `<option value="${k}" ${w.mode === k ? "selected" : ""}>${v}</option>`).join("")}</select>
    ${w.mode === "condition" ? `<label>Bedingung (Template, wahr = anzeigen)</label><textarea data-p="when.condition">${esc(w.condition || "")}</textarea>` : ""}
    ${w.mode === "schedule" ? `<div class="row"><div><label>Tage</label><input data-p="when.days" value="${esc(w.days || "Mo-Fr")}"></div><div><label>von</label><input data-p="when.from" value="${esc(w.from || "")}" placeholder="06:30"></div><div><label>bis</label><input data-p="when.to" value="${esc(w.to || "")}" placeholder="09:00"></div></div>` : ""}
    ${w.mode !== "manual" ? `<label>Höchstens alle … Sekunden an die Tafel senden (schnelle Sensoren)</label><input data-p="when.min_interval" type="number" value="${esc(w.min_interval || 10)}">` : ""}
    ${w.mode !== "manual" ? `<div class="row"><div><label>Nur gelegentlich: alle (s, 0 = immer sichtbar)</label><input data-p="when.every" type="number" value="${esc(w.every || 0)}"></div><div><label>jeweils für (s)</label><input data-p="when.show" type="number" value="${esc(w.show || 10)}"></div></div>` : ""}
    <div class="sub"><h3>Ereignis-Auslöser (zeigt die Kachel sofort)</h3>
      ${(w.events || []).map((e, i) => `<div class="row"><div><label>Entität</label><input data-p="when.events.${i}.entity" value="${esc(e.entity || "")}" list="ents"></div><div><label>wechselt zu (leer = jede Änderung)</label><input data-p="when.events.${i}.to" value="${esc(e.to || "")}"></div><div><label>&nbsp;</label><button class="ghost" data-delev="${i}">entfernen</button></div></div>`).join("")}
      <p><button class="ghost" id="addev">+ Auslöser</button></p></div>
    <label>Sprachbefehl (Notiz für das Polyglot-Gate)</label><input data-p="when.voice" value="${esc(w.voice || "")}" placeholder="zeig die PV auf der Tafel">
    <p class="hint">Knopf, Sprache, Automation: Aktion <code>perron_studio.show</code> mit <code>tile: ${esc(t.name)}</code>.</p>
    <h2 style="margin-top:20px">Wo &amp; wie lange</h2>
    <div class="seg">${Object.entries(ZONES).map(([k, v]) => `<span data-zone="${k}" class="${wh.zone === k ? "on" : ""}">${v}</span>`).join("")}</div>
    <div class="row"><div><label>Dauer bei Abruf/Ereignis (s)</label><input data-p="where.duration" type="number" value="${esc(wh.duration || 20)}"></div>
    <div><label>Wichtigkeit</label><select data-p="where.prio">${Object.entries(PRIO).map(([k, v]) => `<option value="${k}" ${String(wh.prio) === k ? "selected" : ""}>${v}</option>`).join("")}</select></div></div>
  </section>
  <section class="card sticky">
    <h2>Vorschau <span class="chip">von der Tafel gerendert</span></h2>
    <img class="led" id="prev" alt="Vorschau">
    <div class="seg" style="margin-top:10px">${Object.entries(ZONES).map(([k, v]) => `<span data-pz="${k}" class="${this.zone === k ? "on" : ""}">${v}</span>`).join("")}</div>
    <div class="err" id="perr"></div>
    <p class="hint">Mit den aktuellen Werten aus Home Assistant – genau so zeigt es die Tafel. Zu lange Texte laufen auf der Tafel durch.</p>
  </section>
</div>`;
    const $ = (s) => main.querySelector(s);
    const all = (s) => main.querySelectorAll(s);
    const setPath = (path, val) => {
      const keys = path.split(".");
      let o = this.edit;
      for (let i = 0; i < keys.length - 1; i++) {
        const k = keys[i], nk = keys[i + 1];
        if (o[k] == null) o[k] = /^\d+$/.test(nk) ? [] : {};
        o = o[k];
      }
      o[keys[keys.length - 1]] = val;
    };
    all("[data-k]").forEach((el) => (el.oninput = () => { this.edit[el.dataset.k] = el.value; this._schedulePreview(); }));
    all("[data-p]").forEach((el) => {
      const ev = el.tagName === "SELECT" ? "onchange" : "oninput";
      el[ev] = () => {
        let v = el.value;
        if (el.type === "number") v = Number(v);
        setPath(el.dataset.p, v);
        if (el.dataset.p === "when.mode") return this._renderEditor();
        this._schedulePreview();
      };
    });
    all("[data-tpl]").forEach((el) => (el.onclick = () => { this.edit.template = el.dataset.tpl; this._renderEditor(); }));
    all("[data-zone]").forEach((el) => (el.onclick = () => { this.edit.where.zone = el.dataset.zone; this.zone = el.dataset.zone; this._renderEditor(); }));
    all("[data-pz]").forEach((el) => (el.onclick = () => { this.zone = el.dataset.pz; all("[data-pz]").forEach((x) => x.classList.toggle("on", x === el)); this._preview(); }));
    all("[data-acc]").forEach((el) => (el.onclick = () => { this.edit.accent = el.dataset.acc; this._renderEditor(); }));
    all("[data-delrow]").forEach((el) => (el.onclick = (e) => { e.preventDefault(); this.edit.rows.splice(+el.dataset.delrow, 1); this._renderEditor(); }));
    all("[data-delev]").forEach((el) => (el.onclick = () => { this.edit.when.events.splice(+el.dataset.delev, 1); this._renderEditor(); }));
    const addrow = $("#addrow");
    if (addrow) addrow.onclick = () => { this.edit.rows.push({}); this._renderEditor(); };
    $("#addev").onclick = () => { (this.edit.when.events = this.edit.when.events || []).push({ entity: "", to: "" }); this._renderEditor(); };
    $("#back").onclick = () => this._renderList();
    $("#save").onclick = () => this._save(this.edit);
    $("#shownow").onclick = async () => {  // save first: the automation shows what is saved
      if ((await this._save(this.edit, false)) === false) return;
      this._showNow(this.edit);
    };
    $("#del").onclick = async () => {
      if (!confirm(`Kachel „${this.edit.name}“ löschen?`)) return;
      await this._hass.callApi("DELETE", `perron_studio/tiles?id=${encodeURIComponent(this.edit.id)}`);
      this.tiles = this.tiles.filter((t) => t.id !== this.edit.id);
      this._renderList();
    };
    this._preview();
  }

  _schedulePreview() {
    clearTimeout(this._pt);
    this._pt = setTimeout(() => this._preview(), 600);
  }

  async _preview() {
    const img = this.shadowRoot.getElementById("prev");
    const err = this.shadowRoot.getElementById("perr");
    if (!img || !this.edit) return;
    try {
      const u = await this._img("POST", "perron_studio/preview", { tile: this.edit, zone: this.zone });
      if (this._prevUrl) URL.revokeObjectURL(this._prevUrl);
      this._prevUrl = u; img.src = u;
      err.textContent = this._night
        ? "Tafel ist gerade im Nachtmodus: Vorschau zeigt das Tag-Layout. Nachts erscheinen nur Klingel, Alarme und Kacheln, die du jetzt abrufst (dann als Vollbild)."
        : "";
    } catch (e) {
      err.textContent = e.message || String(e);
    }
  }
}

customElements.define("perron-studio-panel", PerronStudioPanel);
