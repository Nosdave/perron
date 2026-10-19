// Perron – Home Assistant cards v1: model, JSON parser, image slots. Drawing: perron_cards_draw.h.
// Spec: docs/cards.md. Everything here runs on the main loop (API actions + renderer), so no lock;
// only prio-0 alarms go through the locked model (perron_core.h push_card).
#pragma once

#include <algorithm>
#include <cstring>
#include <functional>
#include <string>
#include <vector>

#include "esp_heap_caps.h"
#include "mbedtls/base64.h"
#include "esphome/core/color.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"

#include "perron_core.h"
#include "perron_icons.h"

namespace perron {

enum CardTpl : uint8_t { T_HERO, T_PROG, T_LIST, T_MSG, T_KPI, T_RING, T_IMG, T_CV, T_AGENDA, T_N };
static const char *const TPL_NAMES[T_N] = {"hero", "prog", "list", "msg", "kpi", "ring", "img", "cv", "agenda"};

// Colour tokens (HA never sends hex): w s a r rc nv w2 w4 + tag names.
// accent colours for cards: y yellow, g green, b blue, v violet (amber/red stay reserved for departures)
enum Tok : uint8_t { K_W, K_S, K_A, K_R, K_RC, K_NV, K_W2, K_W4, K_CAL, K_COM, K_WX, K_DIS, K_ALR, K_NEWS, K_HA,
                     K_Y, K_G, K_B, K_V, K_N };
static const char *const TOK_NAMES[K_N] = {"w", "s", "a", "r", "rc", "nv", "w:2", "w:4",
                                            "cal", "com", "wx", "dis", "alr", "news", "ha", "y", "g", "b", "v"};
// Fonts (whitelist, never scaled)
enum FontTok : uint8_t { FT_TINY, FT_SMALL, FT_MID, FT_DEST, FT_BIG, FT_CLOCK, FT_N };
static const char *const FONT_NAMES[FT_N] = {"tiny", "small", "mid", "dest", "big", "clock"};

struct CardEl {      // canvas element: t text | n number | i icon | b chip | r rect | g bar | m image
  char t = 't';
  int16_t x = 0, y = 0, w = 0, h = 0;
  int16_t pct = 0;
  uint8_t col = K_W, font = FT_SMALL, size = 7;
  bool fill = false;
  std::string s;     // text / icon name / image slot
};
struct ListRow { std::string ic, label, val; uint8_t col = K_W; };
struct KpiCell { std::string label, val, unit, sub, ic; uint8_t col = K_W; int pct = -1; };

struct HaCard {
  std::string id;
  CardTpl t = T_MSG;
  char z = 'a';              // f full | p panel | l pager | a auto (from prio)
  uint8_t p = 2;             // 1 event, 2 state, 3 ambient (0 = alarm, routed to the model)
  char s = 'i';              // severity: i info | a attention | x alarm
  uint8_t tag = K_HA;
  uint8_t ac = K_N;          // accent token (K_N = from the tag colour)
  uint32_t ttl = 0, hold = 15, expires = 0;
  uint32_t every = 0, show = 10;  // occasional: visible `show` s every `every` s (0 = always)
  uint32_t since_ms = 0;     // when the content last changed (p1 hold window)
  uint32_t at = 0;           // epoch of the last content change (shown on ring cards)
  uint32_t hash = 0;
  std::string ic, ti, val, u, sub, ft, img;
  int pct = -1;
  bool fb = false;           // img: full bleed 192x64 (max 10 s)
  char fit = 0;              // image fit: 'c' cover (fill + crop), 'l' letterbox (whole image); 0 = template default
  int fy = 50;               // cover: vertical crop position 0 (top) .. 100 (bottom)
  std::vector<ListRow> rows;
  std::vector<KpiCell> kpi;
  std::vector<CardEl> el;
};

inline std::vector<HaCard> &ha_cards() { static std::vector<HaCard> v; return v; }
inline uint32_t &cards_gen() { static uint32_t g = 0; return g; }
// Last parser / image result, published as the "Kartenstatus" text sensor.
inline std::string &card_status() { static std::string s = "-"; return s; }

static int tok(const char *s, int def = K_W) {
  if (!s || !*s) return def;
  for (int i = 0; i < K_N; i++)
    if (strcmp(s, TOK_NAMES[i]) == 0) return i;
  return -1;
}
static int font_tok(const char *s, int def = FT_SMALL) {
  if (!s || !*s) return def;
  for (int i = 0; i < FT_N; i++)
    if (strcmp(s, FONT_NAMES[i]) == 0) return i;
  return -1;
}
static std::string jstr(JsonVariantConst v, size_t max_chars = 64) {
  std::string s;
  if (v.is<const char *>()) s = v.as<const char *>();
  else if (v.is<long>()) s = std::to_string(v.as<long>());
  else if (v.is<float>()) { char b[24]; snprintf(b, sizeof(b), "%g", v.as<float>()); s = b; }
  s = led_safe(s);
  // cut at max_chars UTF-8 characters
  size_t n = 0, i = 0;
  while (i < s.size() && n < max_chars) {
    unsigned char c = s[i];
    i += c < 0x80 ? 1 : (c >> 5) == 6 ? 2 : (c >> 4) == 14 ? 3 : 4;
    n++;
  }
  return s.substr(0, std::min(i, s.size()));
}

// ------------------------------------------------------------------ image slots (PSRAM, RGB565)
struct ImgSlot {
  std::string key;
  uint16_t w = 0, h = 0;
  uint16_t *px = nullptr;    // RGB565, row-major
  bool url = false;          // drawn by an online_image component (PNG/BMP from a URL)
  uint8_t url_fmt = 0;       // 0 png, 1 bmp, 2 jpeg
  bool ready = false;
};
inline std::vector<ImgSlot> &img_slots() { static std::vector<ImgSlot> v; return v; }
// Set from YAML: draws the URL image of the given format at x,y (online_image components).
inline std::function<void(void *display, uint8_t fmt, int x, int y)> &url_drawer() {
  static std::function<void(void *, uint8_t, int, int)> f;
  return f;
}
inline std::function<void(uint8_t fmt, const std::string &url)> &url_loader() {
  static std::function<void(uint8_t, const std::string &)> f;
  return f;
}
static const size_t MAX_SLOTS = 3;

static ImgSlot *slot(const std::string &key, bool create) {
  auto &v = img_slots();
  for (auto &s : v)
    if (s.key == key) return &s;
  if (!create) return nullptr;
  if (v.size() >= MAX_SLOTS) {  // drop the oldest slot
    free(v.front().px);
    v.erase(v.begin());
  }
  v.push_back(ImgSlot{});
  v.back().key = key;
  return &v.back();
}

struct ImgRx { std::string key; uint8_t *buf = nullptr; size_t cap = 0, off = 0; int next = 0, total = 0, w = 0, h = 0; };
inline ImgRx &img_rx() { static ImgRx r; return r; }

// Keep images calm on the LEDs: mean luminance <= 35 % (scales all pixels down if brighter).
static void clamp_luma(uint16_t *px, size_t n) {
  if (!n) return;
  uint64_t sum = 0;
  for (size_t i = 0; i < n; i++) {
    uint16_t c = px[i];
    int r = (c >> 11) << 3, g = ((c >> 5) & 0x3F) << 2, b = (c & 0x1F) << 3;
    sum += (r * 77 + g * 150 + b * 29) >> 8;
  }
  uint32_t mean = sum / n;  // 0..255
  if (mean <= 89) return;
  uint32_t k = 89 * 256 / mean;
  for (size_t i = 0; i < n; i++) {
    uint16_t c = px[i];
    uint32_t r = ((c >> 11) * k) >> 8, g = (((c >> 5) & 0x3F) * k) >> 8, b = ((c & 0x1F) * k) >> 8;
    px[i] = (r << 11) | (g << 5) | b;
  }
}

// API action push_image: raw RGB565 little-endian, base64, in chunks (API frames are max 32 KB;
// 8 KB raw per chunk = 3 calls for 192x64). seq 0..total-1, same connection -> in order.
inline bool push_image_chunk(const std::string &key, int seq, int total, int w, int h, const std::string &b64) {
  ImgRx &rx = img_rx();
  const size_t need = size_t(w) * h * 2;
  if (key.empty() || w <= 0 || h <= 0 || w > 192 || h > 64 || total < 1 || total > 16) {
    card_status() = "Bild: ungültige Größe/Teile";
    return false;
  }
  if (seq == 0) {
    if (rx.cap < need) {
      heap_caps_free(rx.buf);
      rx.buf = (uint8_t *) heap_caps_malloc(need, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
      rx.cap = rx.buf ? need : 0;
    }
    rx.key = key; rx.off = 0; rx.next = 0; rx.total = total; rx.w = w; rx.h = h;
  }
  if (!rx.buf || seq != rx.next || rx.key != key || rx.w != w || rx.h != h) {
    rx.next = -1;
    card_status() = "Bild: Teil " + std::to_string(seq) + " außer Reihenfolge";
    return false;
  }
  size_t n = 0;
  if (mbedtls_base64_decode(rx.buf + rx.off, rx.cap - rx.off, &n, (const uint8_t *) b64.data(), b64.size()) != 0) {
    rx.next = -1;
    card_status() = "Bild: base64-Fehler";
    return false;
  }
  rx.off += n;
  if (++rx.next < total) return true;
  if (rx.off != need) {
    card_status() = "Bild: " + std::to_string(rx.off) + " statt " + std::to_string(need) + " Bytes";
    return false;
  }
  ImgSlot *s = slot(key, true);
  if (s->url || s->w != w || s->h != h || !s->px) {
    heap_caps_free(s->px);
    s->px = (uint16_t *) heap_caps_malloc(need, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  }
  if (!s->px) { card_status() = "Bild: kein Speicher"; return false; }
  memcpy(s->px, rx.buf, need);
  s->w = w; s->h = h; s->url = false; s->ready = true;
  clamp_luma(s->px, size_t(w) * h);
  cards_gen()++;
  card_status() = "Bild " + key + " " + std::to_string(w) + "x" + std::to_string(h) + " ok";
  return true;
}

// API action push_image_url: the board downloads a PNG, JPEG or BMP (e.g. HA entity_picture with its
// short-lived token). One URL image at a time per format.
inline void push_image_url(const std::string &key, const std::string &url) {
  if (url.rfind("http://", 0) != 0 && url.rfind("https://", 0) != 0) { card_status() = "Bild-URL: nur http(s)"; return; }
  std::string low = url;
  for (auto &c : low) c = tolower(c);
  uint8_t fmt = 0;
  if (low.find(".bmp") != std::string::npos || low.find("format=bmp") != std::string::npos) fmt = 1;
  else if (low.find("camera_proxy") != std::string::npos || low.find(".jpg") != std::string::npos ||
           low.find(".jpeg") != std::string::npos || low.find("format=jpg") != std::string::npos) fmt = 2;
  for (auto &s : img_slots())  // a format has one decoder: the previous slot of that format goes
    if (s.url && s.url_fmt == fmt && s.key != key) s.ready = false;
  ImgSlot *s = slot(key, true);
  heap_caps_free(s->px);
  s->px = nullptr;
  s->url = true; s->url_fmt = fmt; s->ready = false; s->w = 0; s->h = 0;
  if (url_loader()) url_loader()(fmt, url);
  card_status() = std::string("Bild-URL ") + (fmt == 2 ? "JPEG" : fmt ? "BMP" : "PNG") + " lädt";
}
// called from on_download_finished of the online_image components: copies the decoded image
// (fits 192x192, aspect kept) into the waiting slot as RGB565, so it can be scaled/cropped at
// draw time like pushed pixels; the component buffer is released afterwards (YAML).
inline void url_image_store(uint8_t fmt, int w, int h, const std::function<esphome::Color(int, int)> &px) {
  if (w <= 0 || h <= 0) return;
  for (auto &s : img_slots()) {
    if (!s.url || s.url_fmt != fmt || s.ready) continue;
    heap_caps_free(s.px);
    s.px = (uint16_t *) heap_caps_malloc(size_t(w) * h * 2, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!s.px) { card_status() = "Bild-URL: kein Speicher"; return; }
    for (int y = 0; y < h; y++)
      for (int x = 0; x < w; x++) {
        esphome::Color c = px(x, y);
        s.px[y * w + x] = ((c.r & 0xF8) << 8) | ((c.g & 0xFC) << 3) | (c.b >> 3);
      }
    clamp_luma(s.px, size_t(w) * h);
    s.w = w; s.h = h; s.ready = true; s.url = false;
    cards_gen()++;
    card_status() = "Bild-URL ok " + std::to_string(w) + "x" + std::to_string(h);
    return;
  }
}
inline void url_image_done(uint8_t fmt, bool ok, int w, int h) {
  if (ok) return;  // success is handled by url_image_store
  for (auto &s : img_slots())
    if (s.url && s.url_fmt == fmt) s.ready = false;
  card_status() = "Bild-URL Fehler";
}

// ------------------------------------------------------------------ JSON card parser
static uint32_t fnv(const std::string &s, uint32_t h = 2166136261u) {
  for (unsigned char c : s) h = (h ^ c) * 16777619u;
  return h;
}

// Canvas guard rails: max 8 elements, 1 image, one clock-font number per 64 px column,
// everything inside the safe area of its zone. Any violation rejects the whole card.
static std::string validate_canvas(const HaCard &c) {
  if (c.el.empty()) return "Canvas ohne Elemente";
  if (c.el.size() > 8) return "Canvas: max. 8 Elemente";
  int imgs = 0, clock_cols[3] = {0, 0, 0};
  bool panel = c.z == 'p';
  int x0 = panel ? 130 : 1, x1 = panel ? 190 : 190, y0 = panel ? 0 : 11, y1 = panel ? 63 : 55;
  for (auto &e : c.el) {
    if (e.t == 'm') imgs++;
    if (e.font == FT_CLOCK && (e.t == 't' || e.t == 'n')) clock_cols[std::min(2, std::max(0, e.x / 64))]++;
    int w = std::max<int>(e.w, 1), h = std::max<int>(e.h, 1);
    if (e.t == 'i') w = h = e.size;
    if (e.x < x0 || e.y < y0 || e.x + w - 1 > x1 || e.y + h - 1 > y1) return "Canvas: Element außerhalb der Fläche";
    if (e.t == 'r' && e.fill && e.w * e.h > (x1 - x0 + 1) * (y1 - y0 + 1) / 8) return "Canvas: Füllfläche > 1/8";
  }
  if (imgs > 1) return "Canvas: max. 1 Bild";
  for (int k : clock_cols)
    if (k > 1) return "Canvas: max. 1 große Zahl pro Panel";
  return "";
}

// Forward: prio-0 alarms reuse the alert path of perron_core.h.
inline std::string card_json(const std::string &json) {
  JsonDocument doc(PsramAllocator::instance());
  if (json.size() > 3000) return card_status() = "Karte: JSON zu groß (max. 3000)";
  DeserializationError de = deserializeJson(doc, json);
  if (de) return card_status() = std::string("Karte: JSON-Fehler ") + de.c_str();
  JsonObjectConst o = doc.as<JsonObjectConst>();
  std::string id = jstr(o["id"], 32);
  if (id.empty()) return card_status() = "Karte: id fehlt";
  auto &v = ha_cards();
  auto it = std::find_if(v.begin(), v.end(), [&](const HaCard &c) { return c.id == id; });
  if (o["del"] | 0) {
    if (it != v.end()) v.erase(it);
    push_card("j:" + id, "", 6, 0, 0);  // also clears a prio-0 alarm from this id
    cards_gen()++;
    return card_status() = "Karte " + id + " gelöscht";
  }
  HaCard c;
  c.id = id;
  std::string t = o["t"] | "msg";
  int ti = -1;
  for (int i = 0; i < T_N; i++)
    if (t == TPL_NAMES[i]) ti = i;
  if (ti < 0) return card_status() = "Karte: unbekanntes Template " + t;
  c.t = (CardTpl) ti;
  c.p = std::max(0, std::min(3, (int) (o["p"] | 2)));
  std::string z = o["z"] | "a";
  c.z = (z == "f" || z == "p" || z == "l") ? z[0] : 'a';
  std::string s = o["s"] | "i";
  c.s = (s == "a" || s == "x") ? s[0] : 'i';
  int tg = tok(o["tag"] | "ha", K_HA);
  c.tag = (tg >= K_CAL && tg <= K_HA) ? tg : K_HA;
  int ac = tok(o["ac"] | "", K_N);
  c.ac = ac < 0 ? K_N : ac;
  c.ttl = std::max(0, (int) (o["ttl"] | 0));
  c.hold = std::max(3, std::min(30, (int) (o["hold"] | 15)));
  c.every = std::max(0, std::min(86400, (int) (o["every"] | 0)));
  c.show = std::max(3, std::min(60, (int) (o["show"] | 10)));
  if (c.every && c.every < c.show + 20) c.every = c.show + 20;
  c.ic = jstr(o["ic"], 16);
  c.ti = jstr(o["ti"], 24);
  c.val = jstr(o["val"], 8);
  c.u = jstr(o["u"], 6);
  c.sub = jstr(o["sub"], c.t == T_MSG ? 200 : 40);
  c.ft = jstr(o["ft"], 30);
  c.img = jstr(o["img"], 24);
  c.pct = o["pct"].is<int>() ? std::max(0, std::min(100, o["pct"].as<int>())) : -1;
  c.fb = (o["fb"] | 0) != 0;
  std::string fit = o["fit"] | "";
  c.fit = (fit == "c" || fit == "l") ? fit[0] : 0;
  c.fy = std::max(0, std::min(100, (int) (o["fy"] | 50)));
  for (JsonArrayConst r : o["rows"].as<JsonArrayConst>()) {
    if (c.rows.size() >= (c.t == T_AGENDA ? 8u : 4u)) break;
    ListRow lr;
    lr.ic = jstr(r[0], 16); lr.label = jstr(r[1], 24); lr.val = jstr(r[2], 8);
    int k = tok(r[3] | "w");
    lr.col = k < 0 ? K_W : k;
    c.rows.push_back(lr);
  }
  for (JsonArrayConst r : o["kpi"].as<JsonArrayConst>()) {
    if (c.kpi.size() >= 3) break;
    KpiCell kc;
    kc.label = jstr(r[0], 12); kc.val = jstr(r[1], 5); kc.unit = jstr(r[2], 4);
    int k = tok(r[3] | "w");
    kc.col = k < 0 ? K_W : k;
    kc.pct = r[4].is<int>() ? std::max(0, std::min(100, r[4].as<int>())) : -1;
    kc.sub = jstr(r[5], 16);
    kc.ic = jstr(r[6], 16);
    c.kpi.push_back(kc);
  }
  for (JsonArrayConst e : o["el"].as<JsonArrayConst>()) {
    if (c.el.size() > 8) break;  // validate_canvas rejects
    CardEl ce;
    std::string et = e[0] | "t";
    ce.t = et.empty() ? 't' : et[0];
    ce.x = e[1] | 0; ce.y = e[2] | 0;
    auto colp = [&](JsonVariantConst cv) -> bool { int k = tok(cv | "w"); if (k < 0) return false; ce.col = k; return true; };
    bool ok = true;
    switch (ce.t) {
      case 't': case 'n': {  // ["t",x,y,"text","font","col"]
        ce.s = jstr(e[3], 40);
        int f = font_tok(e[4] | "small");
        if (f < 0) ok = false; else ce.font = f;
        ok = ok && colp(e[5]);
        break;
      }
      case 'i':  // ["i",x,y,"name",size,"col"]
        ce.s = jstr(e[3], 16); ce.size = (e[4] | 7) >= 16 ? 16 : (e[4] | 7) >= 9 ? 9 : 7;
        ok = colp(e[5]);
        break;
      case 'b':  // ["b",x,y,"text","col"]  chip: col fill, white text
        ce.s = jstr(e[3], 12); ok = colp(e[4]); ce.h = 9;
        break;
      case 'r':  // ["r",x,y,w,h,"col",fill]
        ce.w = e[3] | 0; ce.h = e[4] | 0; ok = colp(e[5]); ce.fill = (e[6] | 0) != 0;
        break;
      case 'g':  // ["g",x,y,w,h,pct,"col"]
        ce.w = e[3] | 0; ce.h = e[4] | 0; ce.pct = std::max(0, std::min(100, (int) (e[5] | 0))); ok = colp(e[6]);
        break;
      case 'm':  // ["m",x,y,"slot"]
        ce.s = jstr(e[3], 24);
        break;
      default: ok = false;
    }
    if (!ok) return card_status() = std::string("Canvas: ungültiges Element '") + ce.t + "'";
    ce.x &= ~1; ce.y &= ~1;  // 2 px grid
    c.el.push_back(ce);
  }
  // unknown icon names are not an error (the card still shows), but the status says so
  std::string unknown;
  auto check_icon = [&](const std::string &n) {
    if (n.empty()) return;
    for (auto &i : ICONS7) if (n == i.name) return;
    for (auto &i : ICONS16) if (n == i.name) return;
    for (auto &i : ICONS9) if (n == i.name) return;
    if (unknown.find(n) == std::string::npos) unknown += (unknown.empty() ? "" : ",") + n;
  };
  check_icon(c.ic);
  for (auto &r : c.rows) check_icon(r.ic);
  for (auto &k : c.kpi) check_icon(k.ic);
  for (auto &e : c.el) if (e.t == 'i') check_icon(e.s);
  if (c.t == T_CV) {
    if (c.z == 'a') c.z = c.p == 1 ? 'f' : 'p';
    std::string err = validate_canvas(c);
    if (!err.empty()) return card_status() = err + " (" + id + ")";
  }
  if (c.p == 0) {  // alarm: full-screen takeover via the BE-Alert path, until cleared
    std::string body = c.ti;
    std::string rest = c.sub.empty() ? c.val : c.sub;
    if (!rest.empty()) body += (body.empty() ? "" : ": ") + rest;
    push_card("j:" + id, body, 4, 0, c.ttl);
    if (it != v.end()) v.erase(it);
    cards_gen()++;
    return card_status() = "Alarm " + id + " aktiv";
  }
  uint32_t now = now_epoch();
  c.expires = (c.ttl && now) ? now + c.ttl : 0;
  c.hash = fnv(json);
  c.since_ms = esphome::millis();
  c.at = now;
  if (c.fb) c.hold = std::min<uint32_t>(c.hold, 10);
  if (it != v.end()) {
    if (it->hash == c.hash) { c.since_ms = it->since_ms; c.at = it->at; }  // unchanged re-push: keep the hold window
    *it = c;
  } else {
    if (v.size() >= 8) v.erase(v.begin());
    v.push_back(c);
  }
  cards_gen()++;
  return card_status() = "Karte " + id + " (" + TPL_NAMES[c.t] + ") ok" +
                         (unknown.empty() ? std::string() : ", Icon unbekannt: " + unknown);
}

// Effective zone: explicit f/p/l, or from prio (1 event: full screen for `hold`, then panel;
// 2 state: panel; 3 ambient: pager).
inline char card_zone(const HaCard &c) {
  if (c.z != 'a') return c.z;
  return c.p <= 1 ? 'e' : c.p == 2 ? 'p' : 'l';
}
// One pager line for pager-zone cards: "title: value unit - sub".
inline std::string card_line(const HaCard &c) {
  std::string s = c.ti;
  std::string v = c.val + (c.u.empty() ? "" : " " + c.u);
  if (!v.empty()) s += (s.empty() ? "" : ": ") + v;
  std::string sub = c.sub;
  for (auto &ch : sub) if (ch == '|') ch = ' ';
  if (!sub.empty()) s += (s.empty() ? "" : " - ") + sub;
  return s;
}

inline void expire_cards(uint32_t now) {
  if (!now) return;
  auto &v = ha_cards();
  for (auto &c : v)
    if (c.ttl && !c.expires) c.expires = now + c.ttl;  // pushed before SNTP sync
  size_t n = v.size();
  v.erase(std::remove_if(v.begin(), v.end(), [&](const HaCard &c) { return c.expires && c.expires <= now; }), v.end());
  if (v.size() != n) cards_gen()++;
}

}  // namespace perron

namespace perron {
// "Karten-Demo" button: each press shows the next example card (p1: full screen 12 s, then
// panel until it expires after 60 s). Same parser path as Home Assistant.
inline void card_demo() {
  static int i = 0;
  static const char *const demo[] = {
      R"({"id":"demo","t":"prog","p":1,"hold":12,"ttl":60,"ac":"v","ic":"washer","ti":"Waschen","val":"42'","pct":63,"sub":"Spülen|fertig 14:49","ft":"Demo · Waschmaschine"})",
      R"({"id":"demo","t":"kpi","p":1,"hold":12,"ttl":60,"ti":"Energie","kpi":[["PV jetzt","3.4","kW","y",-1,"Spitze 4.1","sun"],["Heute","18.2","kWh","y",-1,"gestern 15.9","sun"],["Akku","78","%","g",78,"voll 16:20","battery"]],"ft":"Demo · Energie"})",
      R"({"id":"demo","t":"list","p":1,"hold":12,"ttl":60,"ti":"Haus","rows":[["door","Terrassentür offen","12'","a"],["car","Auto lädt","64%","w"],["bell","Post eingeworfen","09:12","s"]],"ft":"Demo · Haus"})",
      R"({"id":"demo","t":"ring","p":1,"hold":12,"ttl":60,"ic":"bell","ti":"Haustür","sub":"Paket · DHL","ft":"Demo · Türklingel"})",
      R"({"id":"demo","t":"msg","p":1,"hold":12,"ttl":60,"tag":"cal","ti":"Müll morgen früh","sub":"Gelber Sack und Papier rausstellen, Abholung ab 06:00. Bitte auch den Glascontainer nicht vergessen.","ft":"Demo · Kalender"})",
      R"({"id":"demo","t":"hero","p":1,"hold":12,"ttl":60,"ac":"b","ic":"car","ti":"Büro","val":"23","u":"min","sub":"via Ring|+4 Stau","ft":"Demo · Fahrzeit"})",
      R"({"id":"demo","t":"agenda","p":1,"hold":12,"ttl":60,"ac":"g","ic":"cal","ti":"Heute","rows":[["cal","Altpapier","ganzt.","s"],["clock","Zahnarzt","14:30","a"],["school","Elternabend","19:00","w"],["cake","Geburtstag Anna","20:00","w"]]})",
      R"({"id":"demo","t":"cv","p":1,"hold":12,"ttl":60,"el":[["i",4,14,"car",16,"w"],["t",26,14,"Auto","dest","w"],["n",26,30,"312","clock","w"],["t",58,38,"km","small","s"],["g",26,50,100,2,78,"w"],["t",128,16,"Ladeziel 90%","small","s"],["b",146,30,"+11 kW","nv"]],"ft":"Demo · Canvas"})",
  };
  card_json(demo[i % (sizeof(demo) / sizeof(demo[0]))]);
  i++;
}
}  // namespace perron
