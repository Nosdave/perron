// Perron – on-device setup & settings UI (served by ESPHome web_server as /0.js).
// No external resources: works without internet (except the optional GPS helper on GitHub Pages,
// which is needed because browsers only allow geolocation on https pages).
(() => {
  const HELPER = "https://nosdave.github.io/perron/setup/";
  const helperUrl = new URLSearchParams(location.search).get("helper") || HELPER;  // ?helper= for testing
  const HELPER_ORIGIN = new URL(helperUrl).origin;

  // ---- entity names (must match esphome/packages/settings.yaml) ----
  const T = (n) => ["text", n], N = (n) => ["number", n], SEL = (n) => ["select", n], SW = (n) => ["switch", n];
  const E = {
    key: T("STIB API-Schlüssel"), points: T("Haltestellen"), lines: T("Linienfilter"),
    station: T("Bahnhof"), tfilter: T("Zugfilter"), pt1n: T("Pendeln 1 Name"), pt1t: T("Pendeln 1 Ziel"), pt1f: T("Pendeln 1 Start"), pt1w: T("Pendeln 1 Zeiten"), pt1a: N("Pendeln 1 Gehzeit zur Start-Haltestelle"), pt1b: N("Pendeln 1 Gehzeit von der Ziel-Haltestelle"),
    pt2a: N("Pendeln 2 Gehzeit zur Start-Haltestelle"), pt2b: N("Pendeln 2 Gehzeit von der Ziel-Haltestelle"),
    pt2n: T("Pendeln 2 Name"), pt2t: T("Pendeln 2 Ziel"), pt2f: T("Pendeln 2 Start"), pt2w: T("Pendeln 2 Zeiten"), router: T("Pendeln Routing-Server"),
    loc: T("Standort"), nsrc: T("Nachrichtenquellen"), dfilter: T("Zielfilter"), alias: T("Kurznamen"), night: T("Nachtzeit"), free: T("Freitext"),
    layout: SEL("Layout"), lang: SEL("Sprache"), nmode: SEL("Nachtmodus"),
    badges: SEL("Helle Linien"), scroll: SEL("Laufschrift"),
    b1: N("Helligkeit bei 1 lx (dunkel)"), b10: N("Helligkeit bei 10 lx (dämmrig)"), b100: N("Helligkeit bei 100 lx (Raumlicht)"),
    b1000: N("Helligkeit bei 1000 lx (Tageslicht)"), nbright: N("Helligkeit Nachtzeit"), glass: N("Helligkeit Frontscheibe"), walk: N("Gehzeit zur Haltestelle"), wtrain: N("Gehzeit zum Bahnhof"),
    horizon: N("Vorschau"), dwell: N("Infozeile Wechsel"),
    wx: SW("Wetter (KMI)"), bea: SW("BE-Alert"), disr: SW("STIB-Störungen"), news: SW("Schlagzeilen"),
    second: SW("Zweite Abfahrt"), showwalk: SW("Gehzeit anzeigen"), pintrain: SW("Zug immer anzeigen"), sncblogo: SW("SNCB-Logo beim Zug"), autoup: SW("Automatische Updates"), autob: SW("Helligkeit automatisch"), status: SW("Statusleiste"), pager: SW("Infozeile"), freeon: SW("Freitext anzeigen"),
  };
  const enc = encodeURIComponent;
  const url = ([d, n]) => `/${d}/${enc(n)}`;
  const post = (u) => fetch(u, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" } });
  // detail=all: selects only list their options with it
  async function get(e) { try { return await (await fetch(url(e) + "?detail=all")).json(); } catch { return {}; } }
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

  // ---- address / stop search (Transitous geocoder): onPick({lat, lon, name, stop})
  const routerBase = () => (state.router || "https://api.transitous.org").replace(/\/+$/, "");
  function geoSearch(onPick, ph = "Adresse oder Haltestelle suchen …") {
    const inp = h("input", { type: "text", placeholder: ph, autocomplete: "off" });
    const list = h("div", { class: "results" });
    let timer;
    inp.addEventListener("input", () => {
      clearTimeout(timer);
      const q = inp.value.trim();
      if (q.length < 3) { list.innerHTML = ""; return; }
      timer = setTimeout(async () => {
        try {
          const r = await (await fetch(`${routerBase()}/api/v1/geocode?text=${enc(q)}`)).json();
          list.innerHTML = "";
          for (const p of r.slice(0, 6)) {
            const area = (p.areas || []).filter((a) => a.default).map((a) => a.name).join(", ");
            const name = p.type === "STOP" ? `${p.name} (Haltestelle)` : [p.name, area].filter(Boolean).join(", ");
            list.append(h("button", { class: "ghost res", onclick: () => {
              list.innerHTML = ""; inp.value = "";
              onPick({ lat: +p.lat, lon: +p.lon, name: p.name, stop: p.type === "STOP" });
            } }, name));
          }
          if (!r.length) list.append(h("small", {}, "Nichts gefunden."));
        } catch { list.innerHTML = "<small>Suche nicht erreichbar.</small>"; }
      }, 350);
    });
    return [inp, list];
  }

  // Walking time between two points, once, by the routing server (direct walk, no transit).
  async function walkMinutes(a, b) {
    const q = `fromPlace=${a.lat.toFixed(5)},${a.lon.toFixed(5)}&toPlace=${b.lat.toFixed(5)},${b.lon.toFixed(5)}`;
    const r = await (await fetch(`${routerBase()}/api/v1/plan?${q}&directModes=WALK&transitModes=WALK&maxDirectTime=7200`)).json();
    const d = (r.direct || [])[0];
    if (!d) throw new Error("kein Fußweg gefunden");
    const dist = (d.legs || []).reduce((s, l) => s + (l.distance || 0), 0);
    return { min: Math.max(1, Math.round(d.duration / 60)), m: Math.round(dist) };
  }

  // "messen" next to a walking time: asks for an address (used once, NOT stored), measures the
  // walk to/from the stop and offers the result; nothing changes until "übernehmen" is pressed.
  // stopOf() -> {lat, lon, name} | null; dir "to" = address -> stop, "from" = stop -> address.
  function measureWalk(stopOf, dir, apply) {
    const box = h("div", { class: "measure", hidden: true });
    const btn = h("button", { class: "ghost", type: "button", onclick: () => {
      const st = stopOf();
      if (!st) { toast("Erst die Haltestelle wählen"); return; }
      box.hidden = !box.hidden;
      if (box.hidden) return;
      box.innerHTML = "";
      const out = h("div", {});
      const [inp, list] = geoSearch(async (pl) => {
        out.textContent = "misst …";
        try {
          const w = dir === "to" ? await walkMinutes(pl, st) : await walkMinutes(st, pl);
          out.innerHTML = "";
          out.append(h("span", {}, `${pl.name} ${dir === "to" ? "→" : "←"} ${st.name}: ≈ ${w.min} min (${w.m} m) `),
            h("button", { class: "primary", type: "button", onclick: async () => { await apply(w.min); box.hidden = true; } }, "übernehmen"));
        } catch (e) { out.textContent = "Messung nicht möglich: " + e.message; }
      }, dir === "to" ? "Von welcher Adresse? (wird nicht gespeichert)" : "Zu welcher Adresse? (wird nicht gespeichert)");
      box.append(inp, list, out, h("small", {}, "Die Adresse wird nur für diese eine Messung an den Routing-Server geschickt und nirgends gespeichert."));
      inp.focus();
    } }, "📏 messen");
    return [btn, box];
  }

  // a minutes value with "messen": number box + button + measurement area
  function walkField(label, k, stopOf, dir, max = 40) {
    const out = h("b", {}, `${state[k] || 0} min`);
    const inp = h("input", { type: "number", min: 0, max, step: 1, value: state[k] || 0, style: "width:5em" });
    const save = async (v) => { inp.value = v; state[k] = v; out.textContent = `${v} min`; await set(E[k], v); saved(out); };
    inp.addEventListener("change", () => save(Math.max(0, Math.min(max, +inp.value || 0))));
    const [btn, box] = measureWalk(stopOf, dir, save);
    return h("label", { class: "f" }, h("span", {}, label, " ", out), h("span", { class: "row" }, inp, " ", btn), box);
  }

  // ---- commutes by public transport: name, destination/start by address search, time window
  function placeSearch(label, k, hint) {
    const cur = (state[k] || "").split("|")[1] || "";
    const shown = h("b", {}, cur || "–");
    const [inp, list] = geoSearch(async (p) => {
      const v = `${p.lat.toFixed(5)},${p.lon.toFixed(5)}|${p.name}`;
      state[k] = v; await set(E[k], v); shown.textContent = p.name; saved(shown);
    });
    const clear = h("button", { class: "ghost", onclick: async () => { state[k] = ""; await set(E[k], ""); shown.textContent = "–"; } }, "leeren");
    return h("label", { class: "f" }, h("span", {}, label, ": ", shown, " ", clear), inp, list, hint ? h("small", {}, hint) : "");
  }
  const placeOf = (k) => () => {
    const [ll, name] = (state[k] || "").split("|");
    const [lat, lon] = (ll || "").split(",").map(Number);
    return isFinite(lat) && isFinite(lon) && ll ? { lat, lon, name: name || "Haltestelle" } : null;
  };
  function commuteBlock(i) {
    return h("div", { class: "grp-box" },
      h("div", { class: "grp" }, `Pendeln ${i} (Bus & Bahn)`),
      field("Name auf der Tafel", `pt${i}n`, { ph: i === 1 ? "z. B. Büro" : "z. B. Uni" }),
      placeSearch("Ziel", `pt${i}t`),
      walkField("Gehzeit von der Ziel-Haltestelle", `pt${i}b`, placeOf(`pt${i}t`), "from"),
      placeSearch("Start", `pt${i}f`, "Leer = Standort der Tafel."),
      walkField("Gehzeit zur Start-Haltestelle", `pt${i}a`, placeOf(`pt${i}f`), "to"),
      h("p", { class: "hint" }, "Am genauesten und datenschonend: als Start/Ziel die Haltestelle wählen und die Gehzeit einmal messen "
        + "und eintragen – dann verlässt eure Adresse die Tafel nie. 0 min = Start/Ziel ist eine Adresse (auf ~100 m gerundet, der Router rechnet die Gehzeit)."),
      field("Wann anzeigen", `pt${i}w`, { ph: "Mo-Fr 06:30-09:00", hint: "Tage + Zeitfenster, z. B. „Mo-Fr 06:30-09:00“ oder „Sa,So 09:00-12:00“. Ziel leer = aus." }));
  }

  // ---- brightness: curve over the room light, all in one place, with a live readout
  function brightnessGroup() {
    const live = h("b", {}, "…");
    const tick = async () => {
      const u = await get(["sensor", "Helligkeit Umgebung"]), a = await get(["sensor", "Helligkeit aktuell"]);
      live.textContent = `${u.state ?? "–"} → ${a.state ?? "–"}`;
    };
    tick(); const iv = setInterval(() => { if (!document.body.contains(live)) clearInterval(iv); else tick(); }, 5000);
    return h("div", { class: "grp-box" },
      h("div", { class: "grp" }, "Helligkeit"),
      h("p", { class: "hint" }, "Jetzt: ", live, " – Raumhelligkeit (Lichtsensor) → Helligkeit der Tafel"),
      toggle("Automatisch nach Umgebungslicht", "autob", "Aus: die Tafel nutzt den Raumlicht-Wert (100 lx)."),
      range("bei 1 lx (dunkel)", "b1", 1, 100, 1, " %"),
      range("bei 10 lx (dämmrig)", "b10", 1, 100, 1, " %"),
      range("bei 100 lx (Raumlicht)", "b100", 1, 100, 1, " %"),
      range("bei 1000 lx (Tageslicht)", "b1000", 1, 100, 1, " %"),
      range("in der Nachtzeit", "nbright", 1, 50, 1, " %"),
      range("Frontscheibe Lichtdurchlass (Sensor-Korrektur)", "glass", 5, 100, 1, " %"));
  }

  // ---- news sources (codes must match NEWS_SOURCES in perron_core.h) ----
  const NEWS = [
    ["Belgien", [["bt", "Brussels Times · Belgien (EN)"], ["bul", "The Bulletin (EN)"], ["vrt", "VRT NWS (NL)"], ["llb", "La Libre (FR)"]]],
    ["Brüssel", [["btb", "Brussels Times · Brüssel (EN)"], ["bx1", "BX1 · Bruxelles (FR)"]]],
    ["Europa / EU", [["bteu", "Brussels Times · EU (EN)"], ["pol", "Politico Europe (EN)"], ["en", "Euronews (EN)"], ["enb", "Euronews · Wirtschaft (EN)"]]],
    ["Welt", [["btw", "Brussels Times · Welt (EN)"], ["bbc", "BBC World (EN)"]]],
    ["Deutschsprachig", [["ts", "tagesschau · Inland (DE)"], ["tsa", "tagesschau · Ausland (DE)"], ["orf", "ORF (AT)"]]],
  ];
  function newsSources() {
    const box = h("div", { class: "srcs" }, h("span", { class: "hint" }, "Quellen (bis zu 6) – Schlagzeilen laufen abwechselnd:"));
    const cur = () => (state.nsrc || "bt").split(",").map((x) => x.trim()).filter(Boolean);
    for (const [grp, items] of NEWS) {
      box.append(h("div", { class: "grp" }, grp));
      for (const [code, label] of items) {
        const cb = h("input", { type: "checkbox", checked: cur().includes(code) });
        cb.addEventListener("change", async () => {
          let v = cur().filter((c) => c !== code);
          if (cb.checked) v.push(code);
          if (v.length > 6) { cb.checked = false; toast("Maximal 6 Quellen"); return; }
          state.nsrc = v.join(",");
          await set(E.nsrc, state.nsrc);
          saved(cb.parentElement);
        });
        box.append(h("label", { class: "t" }, cb, h("span", {}, label)));
      }
    }
    return box;
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
    if (p.dfilter !== undefined) jobs.push(set(E.dfilter, p.dfilter));
    if (p.station) jobs.push(set(E.station, p.station));
    if (p.location) jobs.push(set(E.loc, p.location));
    if (p.walk !== undefined) jobs.push(set(E.walk, p.walk));
    await Promise.all(jobs);
    await loadAll();
    toast("Übernommen ✓");
    go(p.station && !p.points ? 1 : cur);
  }
  addEventListener("message", (ev) => {
    if (ev.origin !== HELPER_ORIGIN || !ev.data || !ev.data.perron) return;
    applyHelper(ev.data.perron);
  });
  function openHelper() {
    const w = open(`${helperUrl}?ret=${enc(location.origin)}`, "perron-helper");
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

  // ---- departure stops: walking time per stop ("id:min" in Haltestellen), each measurable
  const DATA = new URL("../data/", helperUrl).href;
  let stopsDb = null, stationsDb = null;
  async function db() {
    if (!stopsDb) {
      try {
        const [s, t] = await Promise.all([fetch(DATA + "stops.json").then((r) => r.json()), fetch(DATA + "stations.json").then((r) => r.json())]);
        stopsDb = Object.fromEntries(s.stops.map((x) => [x.id, x]));
        stationsDb = Object.fromEntries(t.stations.map((x) => [x.id, x]));
      } catch { stopsDb = {}; stationsDb = {}; }
    }
  }
  const parsePoints = () => (state.points || "").split(",").map((x) => x.trim()).filter(Boolean)
    .map((x) => { const [id, m] = x.split(":"); return { id: id.trim(), min: m === undefined || m === "" ? "" : +m }; });
  async function savePoints(list) {
    const v = list.map((p) => (p.min === "" ? p.id : `${p.id}:${p.min}`)).join(",");
    state.points = v; await set(E.points, v);
  }
  function stopWalks() {
    const box = h("div", { class: "grp-box" }, h("div", { class: "grp" }, "Gehzeit je Haltestelle"),
      h("small", {}, "Leer = Standardwert unten. „📏 messen“ fragt einmal nach eurer Adresse (wird nicht gespeichert) und schlägt die Gehzeit vor."));
    const rows = h("div", {});
    box.append(rows);
    (async () => {
      await db();
      const pts = parsePoints();
      if (!pts.length) { rows.append(h("small", {}, "Noch keine Haltestellen.")); return; }
      for (const p of pts) {
        const s = stopsDb[p.id] || stopsDb[p.id.replace(/[A-Za-z]+$/, "")];
        const lines = s ? [...new Set(s.l.map((x) => `${x[0]} → ${x[1]}`))].slice(0, 3).join(", ") : "";
        const inp = h("input", { type: "number", min: 0, max: 30, step: 1, value: p.min, placeholder: "Std.", style: "width:5em" });
        const save = async (v) => {
          const all = parsePoints();
          const me = all.find((x) => x.id === p.id);
          if (me) me.min = v;
          inp.value = v;
          await savePoints(all); saved(inp);
        };
        inp.addEventListener("change", () => save(inp.value === "" ? "" : Math.max(0, Math.min(30, +inp.value))));
        const [btn, mbox] = measureWalk(() => (s ? { lat: s.lat, lon: s.lon, name: s.fr } : null), "to", save);
        rows.append(h("div", { class: "f" },
          h("span", {}, h("b", {}, s ? s.fr : p.id), lines ? h("small", {}, lines) : ""),
          h("span", { class: "row" }, inp, " min ", btn), mbox));
      }
    })();
    return box;
  }
  function trainWalk() {
    const k = "wtrain";
    const out = h("b", {}, `${state[k] || 0} min`);
    const inp = h("input", { type: "number", min: 0, max: 30, step: 1, value: state[k] || 0, style: "width:5em" });
    const save = async (v) => { inp.value = v; state[k] = v; out.textContent = `${v} min`; await set(E[k], v); saved(out); };
    inp.addEventListener("change", () => save(Math.max(0, Math.min(30, +inp.value || 0))));
    let st = null;
    db().then(() => { const x = stationsDb[state.station]; if (x) st = { lat: x.lat, lon: x.lon, name: x.name }; });
    const [btn, box] = measureWalk(() => st, "to", save);
    return h("label", { class: "f" }, h("span", {}, "Gehzeit zum Bahnhof ", out), h("span", { class: "row" }, inp, " ", btn), box);
  }

  // ---- steps ----
  const steps = [
    { t: "Haltestellen", b: () => [
      h("p", { class: "lead" }, "Wähle die Haltestellen und Linien, die die Tafel zeigen soll."),
      h("button", { class: "primary", onclick: openHelper }, "📍 Per Handy-Standort vorschlagen"),
      h("p", { class: "hint" }, "Öffnet eine sichere Hilfsseite (GPS geht im Browser nur über https). Dein Standort bleibt auf dem Handy."),
      h("details", {}, h("summary", {}, "Manuell eintragen"),
        field("Haltestellen (STIB-Bahnsteig-IDs)", "points", { ph: "z. B. 1234:1,1235:1,2345:5", hint: "Kommagetrennt, jede Richtung hat eine eigene ID. Optional :Minuten = Gehzeit zu genau dieser Haltestelle." }),
        field("Linienfilter", "lines", { ph: "leer = alle Linien", hint: "z. B. 81,71" }),
        field("Zielfilter", "dfilter", { ph: "z. B. 71=Delta", hint: "Linie nur in Richtung dieser Ziele (Teil des Namens). Mehrere mit ; trennen." }),
        field("Standort (Breite,Länge)", "loc", { ph: "50.85,4.35", hint: "Für Wetter und BE-Alert. Leer = Brüssel-Zentrum." })),
      stopWalks(),
      range("Gehzeit (Standard für Haltestellen ohne eigene Angabe)", "walk", 0, 15, 1, " min"),
    ] },
    { t: "Zug & Pendeln", b: () => [
      h("p", { class: "lead" }, "Optional: SNCB-Abfahrten und Fahrzeit zur Arbeit mit dem Zug (iRail)."),
      h("button", { class: "primary", onclick: openHelper }, "📍 Bahnhof per Handy-Standort vorschlagen"),
      h("p", { class: "hint" }, "Gleiche Hilfsseite wie bei den Haltestellen: die nächsten Bahnhöfe stehen unter „Zug (SNCB)“."),
      field("Bahnhof (iRail-ID)", "station", { ph: "BE.NMBS.0088…", hint: "Mit dem Standort-Assistenten auswählbar." }),
      field("Zugfilter", "tfilter", { ph: "z. B. p2 oder S5,S19", hint: "p2 = nur Gleis 2; Liniennamen oder Ziele, kommagetrennt." }),
      trainWalk(),
      toggle("Zug immer anzeigen", "pintrain", "Reserviert eine Zeile für den nächsten Zug (Zugfilter, z. B. stadteinwärts), auch wenn er später fährt."),
      toggle("SNCB-Logo beim Zug", "sncblogo", "Zeigt das SNCB-Oval-B vor dem Zugziel."),
      commuteBlock(1), commuteBlock(2),
      h("p", { class: "hint" }, "Verbindungen: ", h("a", { href: "https://transitous.org/sources/", target: "_blank" }, "Transitous"),
        " (Fahrplandaten der Verkehrsbetriebe, Karte © OpenStreetMap). Server änderbar unter „Pendeln Routing-Server“ in Home Assistant."),
      h("p", { class: "hint" }, "Auto-Fahrzeiten (Waze) und Kalender kommen über die Home-Assistant-Integration."),
    ] },
    { t: "Daten", b: () => [
      h("p", { class: "lead" }, "Was die Tafel selbst aus dem Internet holt – auch ohne Home Assistant."),
      field("STIB API-Schlüssel", "key", { type: "password", hint: "Kostenlos auf data.belgianmobility.io. Ohne Schlüssel gilt ein knappes gemeinsames Limit pro Internetanschluss." }),
      toggle("Wetter vom KMI/IRM", "wx"),
      toggle("BE-Alert Warnungen für deinen Standort", "bea"),
      h("button", { class: "ghost", onclick: async () => { await post(`/button/${enc("Warnung testen")}/press`); toast("Testwarnung läuft (60 s)"); } }, "Warnanzeige testen"),
      toggle("STIB-Störungen deiner Linien", "disr"),
      toggle("Schlagzeilen", "news"), newsSources(),
      toggle("Freitext anzeigen", "freeon", "Wird von Home Assistant oder hier gesetzt."),
      field("Freitext", "free", { ph: "z. B. Willkommen!" }),
    ] },
    { t: "Darstellung", b: () => [
      choice("Layout", "layout"), choice("Helle Linien", "badges"), choice("Laufschrift", "scroll"), choice("Sprache", "lang"),
      brightnessGroup(),
      toggle("Zweite Abfahrt anzeigen", "second"), toggle("Gehzeit anzeigen (Symbol + Minuten)", "showwalk"), toggle("Statusleiste (Uhr, Wetter)", "status"),
      toggle("Infozeile (Störungen, Termine, Wetter …)", "pager"),
      range("Infozeile wechselt alle", "dwell", 3, 15, 1, " s"),
      range("Abfahrten anzeigen bis", "horizon", 15, 95, 5, " min"),
      choice("Nachtmodus", "nmode"), field("Nachtzeit", "night", { ph: "23:00-06:00" }),
      field("Kurznamen", "alias", { ph: "Gare du Midi=Midi;Gare du Nord=Nord", hint: "Lange Ziele kürzen: Original=Kurz, mit ; getrennt." }),
    ] },
    { t: "Status", b: () => {
      const st = h("pre", { class: "status" }, "…");
      const tick = async () => {
        const j = await get(["text_sensor", "Datenstatus"]);
        st.textContent = (j.state || "").split(" | ").join("\n");
      };
      tick(); clearInterval(window.__dst); window.__dst = setInterval(tick, 5000);
      return [h("p", { class: "lead" }, "Live-Zustand der Datenquellen."), st,
              toggle("Automatische Updates (nachts 3–5 Uhr)", "autoup", "Neue Versionen kommen direkt von GitHub – auch ohne Home Assistant."),
              h("p", { class: "hint" }, "In Home Assistant erscheint die Tafel automatisch (ESPHome) und kann dort ebenfalls eingestellt werden.")];
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
    document.title = "Perron";
    document.body.innerHTML = "";
    document.body.append(h("header", {}, h("div", { class: "logo" }, "PERRON"),
                                      h("div", { class: "sub" }, location.host)), app);
    app.append(h("p", { class: "lead" }, "Lade Einstellungen …"));
    await loadAll();
    go(state.points || state.station ? 4 : 0);   // configured -> straight to status
    readHash();
  }
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", boot); else boot();
})();
