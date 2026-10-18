// Diele Board – on-device setup & settings UI (served by ESPHome web_server as /0.js).
// No external resources: works without internet (except the optional GPS helper on GitHub Pages,
// which is needed because browsers only allow geolocation on https pages).
(() => {
  const HELPER = "https://nosdave.github.io/ha-diele-board/setup/";
  const helperUrl = new URLSearchParams(location.search).get("helper") || HELPER;  // ?helper= for testing
  const HELPER_ORIGIN = new URL(helperUrl).origin;

  // ---- entity names (must match esphome/packages/settings.yaml) ----
  const T = (n) => ["text", n], N = (n) => ["number", n], SEL = (n) => ["select", n], SW = (n) => ["switch", n];
  const E = {
    key: T("STIB API-Schlüssel"), points: T("Haltestellen"), lines: T("Linienfilter"),
    station: T("Bahnhof"), tfilter: T("Zugfilter"), cfrom: T("Pendeln von"), cto: T("Pendeln nach"),
    loc: T("Standort"), alias: T("Kurznamen"), night: T("Nachtzeit"), free: T("Freitext"),
    layout: SEL("Layout"), lang: SEL("Sprache"), nmode: SEL("Nachtmodus"),
    bright: N("Helligkeit"), nbright: N("Helligkeit Nacht"), walk: N("Gehzeit zur Haltestelle"), wtrain: N("Gehzeit zum Bahnhof"),
    horizon: N("Vorschau"), dwell: N("Infozeile Wechsel"),
    wx: SW("Wetter (KMI)"), bea: SW("BE-Alert"), disr: SW("STIB-Störungen"), news: SW("Schlagzeilen"),
    second: SW("Zweite Abfahrt"), autob: SW("Automatische Helligkeit"), status: SW("Statusleiste"), pager: SW("Infozeile"), freeon: SW("Freitext anzeigen"),
  };
  const enc = encodeURIComponent;
  const url = ([d, n]) => `/${d}/${enc(n)}`;
  const post = (u) => fetch(u, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" } });
  async function get(e) { try { return await (await fetch(url(e))).json(); } catch { return {}; } }
  async function set(e, v) {
    const [d] = e;
    if (d === "text" || d === "number") return post(`${url(e)}/set?value=${enc(v)}`);
    if (d === "select") return post(`${url(e)}/set?option=${enc(v)}`);
    if (d === "switch") return post(`${url(e)}/${v ? "turn_on" : "turn_off"}`);
  }

  // ---- tiny DOM helper ----
  const h = (tag, attrs = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "class") el.className = v;
      else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v === true ? "" : v);
    }
    for (const c of kids.flat()) el.append(c instanceof Node ? c : document.createTextNode(c ?? ""));
    return el;
  };

  const state = {};
  async function loadAll() {
    await Promise.all(Object.entries(E).map(async ([k, e]) => {
      const j = await get(e);
      state[k] = e[0] === "switch" ? j.value === true || j.state === "ON" : (j.value ?? j.state ?? "");
      if (e[0] === "select") state[k + "_opts"] = j.option || [];
    }));
  }

  // ---- field factories (save on change, show a tick) ----
  function saved(el) { el.classList.add("saved"); setTimeout(() => el.classList.remove("saved"), 900); }
  const field = (label, k, opts = {}) => {
    const inp = h("input", { type: opts.type || "text", value: k === "key" ? "" : state[k] ?? "", placeholder: opts.ph || "",
      autocomplete: "off", spellcheck: "false" });
    if (k === "key" && state.key === "gesetzt") inp.placeholder = "gesetzt ✓ (leer lassen = unverändert)";
    inp.addEventListener("change", async () => {
      if (k === "key" && !inp.value) return;
      state[k] = inp.value; await set(E[k], inp.value); saved(inp);
      if (k === "key") { inp.value = ""; inp.placeholder = "gesetzt ✓"; }
    });
    return h("label", { class: "f" }, h("span", {}, label), inp, opts.hint ? h("small", {}, opts.hint) : "");
  };
  const range = (label, k, min, max, step, unit) => {
    const out = h("b", {}, `${state[k]}${unit}`);
    const inp = h("input", { type: "range", min, max, step, value: state[k] });
    inp.addEventListener("input", () => (out.textContent = `${inp.value}${unit}`));
    inp.addEventListener("change", async () => { state[k] = inp.value; await set(E[k], inp.value); saved(out); });
    return h("label", { class: "f" }, h("span", {}, label, " ", out), inp);
  };
  const toggle = (label, k, hint) => {
    const inp = h("input", { type: "checkbox", checked: !!state[k] });
    inp.addEventListener("change", async () => { state[k] = inp.checked; await set(E[k], inp.checked); });
    return h("label", { class: "t" }, inp, h("span", {}, label, hint ? h("small", {}, hint) : ""));
  };
  const choice = (label, k) => {
    const s = h("select", {}, (state[k + "_opts"] || []).map(o => h("option", { value: o, selected: o === state[k] }, o)));
    s.addEventListener("change", async () => { state[k] = s.value; await set(E[k], s.value); saved(s); });
    return h("label", { class: "f" }, h("span", {}, label), s);
  };

  // ---- GPS helper round-trip ----
  async function applyHelper(p) {
    if (!p || p.v !== 1) return;
    const jobs = [];
    if (p.points !== undefined) jobs.push(set(E.points, p.points));
    if (p.lines !== undefined) jobs.push(set(E.lines, p.lines));
    if (p.station) jobs.push(set(E.station, p.station));
    if (p.location) jobs.push(set(E.loc, p.location));
    if (p.walk !== undefined) jobs.push(set(E.walk, p.walk));
    await Promise.all(jobs);
    await loadAll();
    toast("Übernommen ✓");
    go(1);
  }
  addEventListener("message", (ev) => {
    if (ev.origin !== HELPER_ORIGIN || !ev.data || !ev.data.diele) return;
    applyHelper(ev.data.diele);
  });
  function openHelper() {
    const w = open(`${helperUrl}?ret=${enc(location.origin)}`, "diele-helper");
    if (!w) toast("Pop-up blockiert – bitte erlauben.");
  }
  function readHash() {
    const m = location.hash.match(/cfg=([A-Za-z0-9_-]+)/);
    if (!m) return;
    try {
      const json = decodeURIComponent(escape(atob(m[1].replace(/-/g, "+").replace(/_/g, "/"))));
      history.replaceState(null, "", location.pathname);
      applyHelper(JSON.parse(json));
    } catch { /* ignore */ }
  }

  function toast(t) {
    const el = h("div", { class: "toast" }, t);
    document.body.append(el);
    setTimeout(() => el.remove(), 2200);
  }

  // ---- steps ----
  const steps = [
    { t: "Haltestellen", b: () => [
      h("p", { class: "lead" }, "Wähle die Haltestellen und Linien, die die Tafel zeigen soll."),
      h("button", { class: "primary", onclick: openHelper }, "📍 Per Handy-Standort vorschlagen"),
      h("p", { class: "hint" }, "Öffnet eine sichere Hilfsseite (GPS geht im Browser nur über https). Dein Standort bleibt auf dem Handy."),
      h("details", {}, h("summary", {}, "Manuell eintragen"),
        field("Haltestellen (STIB-Bahnsteig-IDs)", "points", { ph: "z. B. 1234:1,1235:1,2345:5", hint: "Kommagetrennt, jede Richtung hat eine eigene ID. Optional :Minuten = Gehzeit zu genau dieser Haltestelle." }),
        field("Linienfilter", "lines", { ph: "leer = alle Linien", hint: "z. B. 92,60" }),
        field("Standort (Breite,Länge)", "loc", { ph: "50.80,4.36", hint: "Für Wetter und BE-Alert. Leer = Uccle." })),
      range("Gehzeit (Standard für Haltestellen ohne eigene Angabe)", "walk", 0, 15, 1, " min"),
    ] },
    { t: "Zug & Pendeln", b: () => [
      h("p", { class: "lead" }, "Optional: SNCB-Abfahrten und Fahrzeit zur Arbeit mit dem Zug (iRail)."),
      field("Bahnhof (iRail-ID)", "station", { ph: "BE.NMBS.0088…", hint: "Mit dem Standort-Assistenten auswählbar." }),
      field("Zugfilter", "tfilter", { ph: "z. B. p2 oder S5,S19", hint: "p2 = nur Gleis 2; Liniennamen oder Ziele, kommagetrennt." }),
      range("Gehzeit zum Bahnhof", "wtrain", 0, 30, 1, " min"),
      field("Pendeln von (iRail-ID)", "cfrom", { ph: "BE.NMBS.0088…" }),
      field("Pendeln nach (iRail-ID)", "cto", { ph: "BE.NMBS.0088…" }),
      h("p", { class: "hint" }, "Auto-Fahrzeiten (Waze) und Kalender kommen über die Home-Assistant-Integration."),
    ] },
    { t: "Daten", b: () => [
      h("p", { class: "lead" }, "Was die Tafel selbst aus dem Internet holt – auch ohne Home Assistant."),
      field("STIB API-Schlüssel", "key", { type: "password", hint: "Kostenlos auf data.belgianmobility.io. Ohne Schlüssel gilt ein knappes gemeinsames Limit pro Internetanschluss." }),
      toggle("Wetter vom KMI (Uccle)", "wx"),
      toggle("BE-Alert Warnungen für deinen Standort", "bea"),
      toggle("STIB-Störungen deiner Linien", "disr"),
      toggle("Schlagzeilen (Brussels Times)", "news"),
      toggle("Freitext anzeigen", "freeon", "Wird von Home Assistant oder hier gesetzt."),
      field("Freitext", "free", { ph: "z. B. Willkommen!" }),
    ] },
    { t: "Darstellung", b: () => [
      choice("Layout", "layout"), choice("Sprache", "lang"),
      toggle("Automatische Helligkeit", "autob", "Mit Lichtsensor (VEML7700): regelt zwischen Nacht- und Tageshelligkeit."),
      range("Helligkeit (maximal)", "bright", 5, 255, 5, ""),
      toggle("Zweite Abfahrt anzeigen", "second"), toggle("Statusleiste (Uhr, Wetter)", "status"),
      toggle("Infozeile (Störungen, Termine, Wetter …)", "pager"),
      range("Infozeile wechselt alle", "dwell", 3, 15, 1, " s"),
      range("Abfahrten anzeigen bis", "horizon", 15, 95, 5, " min"),
      choice("Nachtmodus", "nmode"), field("Nachtzeit", "night", { ph: "23:00-06:00" }),
      range("Helligkeit nachts", "nbright", 2, 120, 1, ""),
      field("Kurznamen", "alias", { ph: "Gare du Nord=Nord;Schaerbeek Gare=Schaerbeek", hint: "Lange Ziele kürzen: Original=Kurz, mit ; getrennt." }),
    ] },
    { t: "Status", b: () => {
      const st = h("pre", { class: "status" }, "…");
      const tick = async () => {
        const j = await get(["text_sensor", "Datenstatus"]);
        st.textContent = (j.state || "").split(" | ").join("\n");
      };
      tick(); clearInterval(window.__dst); window.__dst = setInterval(tick, 5000);
      return [h("p", { class: "lead" }, "Live-Zustand der Datenquellen."), st,
              h("p", { class: "hint" }, "Updates kommen über WLAN. In Home Assistant erscheint die Tafel automatisch (ESPHome).")];
    } },
  ];

  let cur = 0;
  const app = h("main", {});
  function go(i) {
    cur = Math.max(0, Math.min(steps.length - 1, i));
    app.innerHTML = "";
    const nav = h("nav", {}, steps.map((s, j) => h("button", { class: j === cur ? "on" : "", onclick: () => go(j) }, `${j + 1}. ${s.t}`)));
    const body = h("section", {}, steps[cur].b());
    const foot = h("div", { class: "foot" },
      cur > 0 ? h("button", { class: "ghost", onclick: () => go(cur - 1) }, "Zurück") : h("span"),
      cur < steps.length - 1 ? h("button", { class: "primary", onclick: () => go(cur + 1) }, "Weiter") : h("span"));
    app.append(nav, body, foot);
    scrollTo(0, 0);
  }

  async function boot() {
    document.title = "Diele Board";
    document.body.innerHTML = "";
    document.body.append(h("header", {}, h("div", { class: "logo" }, "DIELE", h("span", {}, "BOARD")),
                                      h("div", { class: "sub" }, location.host)), app);
    app.append(h("p", { class: "lead" }, "Lade Einstellungen …"));
    await loadAll();
    go(state.points || state.station ? 4 : 0);   // configured -> straight to status
    readHash();
  }
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", boot); else boot();
})();
