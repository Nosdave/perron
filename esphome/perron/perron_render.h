// Perron – renderer. Port of tools/mockup/scenes.py iteration 5 (D1/D2/P0/NIGHT), revised
// after 2 independent agent reviews (fidelity, performance, UX edge cases).
//
// Performance: render() runs every 50 ms. The model is re-snapshotted only when its generation
// changes; rows / pager items / wrapped alert text are rebuilt at most once per second (or on
// change). The 50 ms tick only animates (arrows, pager scroll, alert pages).
// Coordinates: text y = top row of CAPITALS (same convention as the mockup tool).
#pragma once

#include <cstdio>
#include <cstring>
#include <functional>
#include <string>
#include <vector>

#include "esphome/components/display/display.h"
#include "esphome/components/font/font.h"
#include "esphome/core/hal.h"

#include "perron_core.h"
#include "perron_icons.h"
#include "perron_lines.h"
#include "perron_cards.h"

namespace perron {

using esphome::Color;
using esphome::display::Display;
using esphome::display::TextAlign;
using esphome::font::Font;

// ------------------------------------------------------------------ palette (iteration 5)
static const Color C_WARM(0xFF, 0xE9, 0xCC);
static const Color C_SEC(0x7A, 0x74, 0x6C);
static const Color C_CATCH(0xFF, 0xA0, 0x00);
static const Color C_LEAVE(0xFF, 0x3B, 0x1F);
static const Color C_PAGER(0xD8, 0xD2, 0xC8);
static const Color C_NIGHT(0xFF, 0x8A, 0x00);
static const Color C_NIGHT2(0x80, 0x45, 0x00);

enum Tag : uint8_t { TAG_CAL, TAG_COMMUTE, TAG_WX, TAG_DISR, TAG_ALERT, TAG_NEWS, TAG_HA };
static Color tag_color(uint8_t t) {
  switch (t) {
    case TAG_CAL: return Color(0x5A, 0xA0, 0xFF);
    case TAG_COMMUTE: return Color(0x4F, 0xD1, 0xC5);
    case TAG_WX: return Color(0xB4, 0x8C, 0xFF);
    case TAG_DISR: return Color(0xFF, 0x6A, 0x00);
    case TAG_ALERT: return Color(0xFF, 0x3B, 0x1F);
    case TAG_NEWS: return Color(0x9A, 0x94, 0x8C);
    default: return Color(0x41, 0xBD, 0xF5);
  }
}

// ------------------------------------------------------------------ look / layout settings
// Iteration 8 (2nd multi-agent design review): fixed grid, no rotating rows.
//   PREMIUM: status | 2 large rows (first two groups) | split row (next two groups) | pager
//   FOUR:    slim status | 4 equal rows | pager       HERO: status | 2 very large rows | pager
enum Layout : uint8_t { LAYOUT_PREMIUM = 0, LAYOUT_FOUR = 1, LAYOUT_HERO = 2 };
enum NightMode : uint8_t { NIGHT_OFF = 0, NIGHT_DIM = 1, NIGHT_CLOCK = 2, NIGHT_DARK = 3 };

struct Look {
  Layout layout = LAYOUT_PREMIUM;
  bool status_bar = true, pager = true, second = true;
  int walk_min = 3;          // minutes to the stop
  int walk_train_min = 8;    // minutes to the station
  int horizon_min = 60;      // hide departures further away (max 99: 2-digit column)
  int dwell_s = 6;           // pager item duration
  std::string ui_lang = "de";
  NightMode night = NIGHT_DIM;
  int night_from = 23 * 60, night_to = 6 * 60;  // minutes of day
  std::string aliases;       // "Gare du Midi=Midi;Gare du Nord=Nord"
  std::string points;        // "1234:1,2345:5" -> per-stop walking minutes (default walk_min)
  std::string dest_filter;   // "71=Delta;81=Montgomery" -> line only towards matching destinations
  bool show_walk = true;     // pedestrian glyph + walking minutes in every row
  bool pin_train = true;     // always keep one row for the next (filtered) train
  bool free_on = false;
  bool badge_fill = true;    // light lines filled (original) vs outline
  bool sncb_logo = true;     // SNCB "B" oval before train destinations
  int scroll_px = 2;         // pager scroll: px per 50 ms frame (1 = 20 px/s, 2 = 40, 3 = 60)
  std::string free_text;
  uint32_t version = 0;      // bumped by the settings interval when anything changed
};

struct Fonts { Font *small, *mid, *big, *clock, *dest, *tiny; };

inline Look &look() { static Look l; return l; }  // main-loop only (set by settings interval)

// ------------------------------------------------------------------ i18n
struct Strings {
  const char *no_deps, *no_live, *work, *train, *rain_in, *alert, *bealert, *kmi;
  const char *wd[7];
  const char *rain_from, *rain_now, *rain_until, *light, *moderate, *heavy;
};
static const Strings &S(const std::string &lang) {
  static const Strings de = {"Keine Abfahrten", "Keine Live-Daten", "Arbeit", "Zug", "Regen in ca. %d h",
                             "WARNUNG", "BE-ALERT", "KMI", {"So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"},
                             "Regen ab %s", "Regen jetzt", "bis ca. %s", "leicht", "mäßig", "stark"};
  static const Strings fr = {"Pas de départ", "Pas de données", "Travail", "train", "Pluie dans ~%d h",
                             "ALERTE", "BE-ALERT", "IRM", {"di", "lu", "ma", "me", "je", "ve", "sa"},
                             "Pluie dès %s", "Pluie maintenant", "jusqu'à ~%s", "faible", "modérée", "forte"};
  static const Strings nl = {"Geen vertrek", "Geen live-data", "Werk", "trein", "Regen over ~%d u",
                             "ALARM", "BE-ALERT", "KMI", {"zo", "ma", "di", "wo", "do", "vr", "za"},
                             "Regen vanaf %s", "Regen nu", "tot ~%s", "licht", "matig", "zwaar"};
  static const Strings en = {"No departures", "No live data", "Work", "train", "Rain in ~%d h",
                             "ALERT", "BE-ALERT", "RMI", {"Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"},
                             "Rain from %s", "Rain now", "until ~%s", "light", "moderate", "heavy"};
  if (lang == "fr") return fr;
  if (lang == "nl") return nl;
  if (lang == "en") return en;
  return de;
}

// ------------------------------------------------------------------ text helpers
static int cap_h(Font *f, const Fonts &F) {
  if (f == F.clock) return 13;
  if (f == F.big || f == F.dest) return 10;
  if (f == F.mid) return 7;
  if (f == F.tiny) return 5;
  return 6;
}

static int text_w(Font *f, const std::string &s) {
  int w = 0, xo = 0, bl = 0, h = 0;
  f->measure(s.c_str(), &w, &xo, &bl, &h);
  return w;
}

// Draw with y = top of capitals (baseline = cap top + cap height). align: 0 left, 1 center, 2 right.
static void txt(Display &it, const Fonts &F, Font *f, int x, int y, const std::string &s, Color c, int align = 0) {
  TextAlign a = align == 2 ? TextAlign::BASELINE_RIGHT : align == 1 ? TextAlign::BASELINE_CENTER : TextAlign::BASELINE_LEFT;
  it.print(x, y + cap_h(f, F), f, c, a, s.c_str());
}

// UTF-8 helpers (never split a multi-byte sequence).
static size_t u8_len(unsigned char c) { return c < 0x80 ? 1 : (c >> 5) == 6 ? 2 : (c >> 4) == 14 ? 3 : 4; }
static std::string utf8_sub(const std::string &s, size_t from_char, size_t n_chars) {
  size_t i = 0, ch = 0;
  while (i < s.size() && ch < from_char) { i += u8_len(s[i]); ch++; }
  size_t start = std::min(i, s.size());
  ch = 0;
  while (i < s.size() && ch < n_chars) { i += u8_len(s[i]); ch++; }
  return s.substr(start, std::min(i, s.size()) - start);
}
static size_t utf8_chars(const std::string &s) {
  size_t n = 0;
  for (size_t i = 0; i < s.size(); i += u8_len(s[i])) n++;
  return n;
}

// Drop trailing words until it fits; "" if even the first word does not fit.
static std::string fit_words(Font *f, std::string s, int max_w) {
  while (!s.empty() && text_w(f, s) > max_w) {
    size_t p = s.rfind(' ');
    if (p == std::string::npos) return "";
    s.erase(p);
  }
  return s;
}

static std::string short_dest(std::string name, const std::string &aliases) {
  size_t pos = 0;  // alias map "Long=Short;Long2=Short2"
  while (pos < aliases.size()) {
    size_t end = aliases.find(';', pos);
    if (end == std::string::npos) end = aliases.size();
    std::string kv = aliases.substr(pos, end - pos);
    size_t eq = kv.find('=');
    if (eq != std::string::npos && kv.substr(0, eq) == name) return kv.substr(eq + 1);
    pos = end + 1;
  }
  static const char *pre[] = {"Gare De ", "Gare Du ", "Gare de ", "Gare du ", "Gare ", "Station ", "Place ",
                              "Porte De ", "Porte de "};
  for (auto p : pre) {
    size_t n = strlen(p);
    if (name.size() > n + 2 && name.compare(0, n, p) == 0) { name.erase(0, n); break; }
  }
  static const char *suf[] = {" Gare", " Station", " G.", " St.", " S."};
  for (auto s : suf) {
    size_t n = strlen(s);
    if (name.size() > n + 2 && name.compare(name.size() - n, n, s) == 0) { name.erase(name.size() - n); break; }
  }
  return name;
}

// ------------------------------------------------------------------ icons
template<size_t N> static const Icon *find_icon(const Icon (&tab)[N], const char *name) {
  for (auto &i : tab)
    if (strcmp(i.name, name) == 0) return &i;
  return nullptr;
}

static void icon(Display &it, int x, int y, const char *name, int size, const Color *tint = nullptr) {
  const Icon *ic = size == 16 ? find_icon(ICONS16, name) : size == 9 ? find_icon(ICONS9, name) : find_icon(ICONS7, name);
  if (!ic && size == 16) {  // no 16 px version: draw the 7 px icon doubled (14x14, centred)
    const Icon *s = find_icon(ICONS7, name);
    if (!s) return;
    int ox = x + (16 - s->w * 2) / 2, oy = y + 1;
    for (int j = 0; j < s->h; j++)
      for (int i = 0; i < s->w; i++)
        if (s->px[j * s->w + i] != '.') it.filled_rectangle(ox + i * 2, oy + j * 2, 2, 2, tint ? *tint : Color(235, 235, 235));
    return;
  }
  if (!ic) return;
  for (int j = 0; j < ic->h; j++)
    for (int i = 0; i < ic->w; i++) {
      char k = ic->px[j * ic->w + i];
      if (k == '.') continue;
      if (tint) { it.draw_pixel_at(x + i, y + j, *tint); continue; }  // tinted: every lit pixel
      for (auto &p : ICON_PALETTE)
        if (p.k == k) { it.draw_pixel_at(x + i, y + j, Color(p.r, p.g, p.b)); break; }
    }
}

static const char *ww_condition(int ww, bool night) {
  switch (ww) {
    case 0: case 1: return night ? "clear-night" : "sunny";
    case 3: return night ? "partlycloudy-night" : "partlycloudy";
    case 14: case 15: return "cloudy";
    case 18: case 21: return "rainy";
    case 4: case 6: case 16: case 19: return "pouring";
    case 2: case 5: case 7: case 10: case 13: case 17: return "lightning-rainy";
    case 8: case 9: case 20: return "snowy-rainy";
    case 11: case 12: case 22: case 23: return "snowy";
    case 24: case 25: case 26: case 27: return "fog";
    default: return "cloudy";
  }
}

// ------------------------------------------------------------------ badges
static const LineStyle *line_style(const std::string &line) {
  for (auto &l : LINE_STYLES)
    if (line == l.name) return &l;
  return nullptr;
}

// Brand badge. White-text lines: filled rounded square. Dark-text (light) lines: LEDs bloom
// over black text, so draw a 1-px frame + text in the line colour. SNCB: pill corners.
static void badge(Display &it, const Fonts &F, int x, int y, const std::string &line, int w = 22, int h = 12,
                  Font *f = nullptr, bool night = false) {
  f = f ? f : F.mid;
  const LineStyle *ls = line_style(line);
  uint32_t rgb = ls ? ls->rgb : 0x5A5A5A;
  Color bg((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF);
  // light lines (brand text black): filled like the original, or outline only (setting)
  bool dark = ls && ls->dark_text;
  bool outline = night || (dark && !look().badge_fill) || rgb == 0x000000;
  if (night) bg = C_NIGHT;
  else if (rgb == 0x000000) bg = Color(0x9A, 0x94, 0x8C);  // S10 is black: grey outline
  int tw = text_w(f, line);
  if (tw + 4 > w) w = tw + 4;
  it.filled_rectangle(x, y, w, h, bg);
  if (outline) it.filled_rectangle(x + 1, y + 1, w - 2, h - 2, Color::BLACK);
  const int corners[4][2] = {{0, 0}, {w - 1, 0}, {0, h - 1}, {w - 1, h - 1}};
  for (auto &p : corners) it.draw_pixel_at(x + p[0], y + p[1], Color::BLACK);
  if (ls && ls->kind == TRAIN) {
    const int px[8][2] = {{1, 0}, {w - 2, 0}, {1, h - 1}, {w - 2, h - 1}, {0, 1}, {w - 1, 1}, {0, h - 2}, {w - 1, h - 2}};
    for (auto &p : px) it.draw_pixel_at(x + p[0], y + p[1], Color::BLACK);
    if (outline) {  // keep the frame closed around the rounded corners
      it.draw_pixel_at(x + 1, y + 1, bg); it.draw_pixel_at(x + w - 2, y + 1, bg);
      it.draw_pixel_at(x + 1, y + h - 2, bg); it.draw_pixel_at(x + w - 2, y + h - 2, bg);
    }
  }
  txt(it, F, f, x + (w - tw + 1) / 2, y + (h - cap_h(f, F)) / 2, line, outline ? bg : dark ? Color::BLACK : Color(255, 255, 255));
}

// STIB-style "arriving" signal: two down-arrows bouncing 1 px.
static void arrows_now(Display &it, int x_right, int y, Color c) {
  int phase = (esphome::millis() / 400) % 2;
  static const char *rows[3] = {"#####", ".###.", "..#.."};
  for (int k = 0; k < 2; k++) {
    int ax = x_right - 15 + k * 8, ay = y + 1 + phase;
    for (int i = 0; i < 3; i++)
      for (int j = 0; j < 5; j++)
        if (rows[i][j] == '#') {
          it.draw_pixel_at(ax + j, ay + i * 2, c);
          it.draw_pixel_at(ax + j, ay + i * 2 + 1, c);
        }
  }
}

// ------------------------------------------------------------------ frame cache
struct Row {
  std::string key;        // group identity: "line|pointid" (STIB platform) or "~train"
  std::string point;      // STIB pointid ("" for trains)
  std::string line, dest;
  std::vector<int> mins;  // catchable departures within the preview, ascending (may be empty)
  uint32_t next_epoch = 0;  // first departure beyond the preview (shown as HH:MM), 0 = unknown
  int walk = 0;           // walking minutes for this row (stop or station)
  int order = 0;          // position of its stop in the configuration (train last)
  int delay_min = 0;
  int missed = -1;           // minutes of a reported but no longer catchable vehicle (shown grey)
  uint32_t plan_epoch = 0;   // trains: scheduled departure (without delay)
  bool canceled = false, train = false, stale = false;
};
struct PagerItem { uint8_t tag; std::string text; uint8_t prio; std::string key; int width; };

struct Frame {
  uint32_t model_gen = 0xFFFFFFFF, look_ver = 0xFFFFFFFF, built_s = 0;
  Model m;                       // cached snapshot (re-taken only on generation change)
  std::vector<Row> rows;
  std::vector<PagerItem> pager;
  std::string p0_title, p0_body;
  std::vector<std::string> p0_lines;
  bool train_stale = false, stib_stale = false, any_data = false;
};
inline Frame &frame() { static Frame f; return f; }

static bool stale_src(const Model &m, Src s, uint32_t now, uint32_t max_age) {
  return !now || !m.ts[s] || now < m.ts[s] || now - m.ts[s] > max_age;
}

static int stop_walk(const Look &L, const std::string &point) {
  for (auto &t : split_csv(L.points)) {
    size_t c = t.find(':');
    if (c != std::string::npos && t.compare(0, c, point) == 0) return atoi(t.c_str() + c + 1);
  }
  return L.walk_min;
}

// "71=Delta;81=Montgomery": a listed line is only shown towards destinations containing
// one of its values (case-insensitive substring). Unlisted lines are unaffected.
static bool dest_allowed(const Look &L, const std::string &line, const std::string &dest) {
  if (L.dest_filter.empty()) return true;
  auto lower = [](std::string x) {
    for (auto &c : x) c = (char) tolower((unsigned char) c);
    return x;
  };
  bool listed = false;
  std::string d = lower(dest);
  size_t pos = 0;
  while (pos < L.dest_filter.size()) {
    size_t end = L.dest_filter.find(';', pos);
    if (end == std::string::npos) end = L.dest_filter.size();
    std::string kv = L.dest_filter.substr(pos, end - pos);
    size_t eq = kv.find('=');
    if (eq != std::string::npos && kv.substr(0, eq) == line) {
      listed = true;
      std::string want = lower(kv.substr(eq + 1));
      if (!want.empty() && d.find(want) != std::string::npos) return true;
    }
    pos = end + 1;
  }
  return !listed;
}

static int point_order(const Look &L, const std::string &point) {
  auto t = split_csv(L.points);
  for (size_t i = 0; i < t.size(); i++) {
    size_t c = t[i].find(':');
    if ((c == std::string::npos ? t[i] : t[i].substr(0, c)) == point) return (int) i;
  }
  return 500;
}

// Fixed rows (iteration 7): every line/direction that was seen keeps its row (in the order of
// the configured stops, train last), even when it has no departure in the preview window.
struct GroupMem {
  std::string key, point, line, dest;
  bool train;
  int order, walk;
  uint32_t seen;
};
inline std::vector<GroupMem> &groups() { static std::vector<GroupMem> g; return g; }

// Persistence across reboots (wired up in YAML to a restore_value global):
//   blob = "<cfg hash>\n" + per group "key\tline\tdest\ttrain\torder\twalk\n"
inline std::string &groups_boot_blob() { static std::string b; return b; }
inline std::function<void(const std::string &)> &groups_saver() {
  static std::function<void(const std::string &)> f;
  return f;
}
static uint32_t fnv1a(const std::string &s) {
  uint32_t h = 2166136261u;
  for (unsigned char c : s) { h ^= c; h *= 16777619u; }
  return h;
}
static std::string groups_serialize(const std::string &ck) {
  std::string o = std::to_string(fnv1a("v2|" + ck)) + "\n";
  for (auto &g : groups())
    o += g.key + "\t" + g.point + "\t" + g.line + "\t" + g.dest + "\t" + (g.train ? "1" : "0") + "\t" +
         std::to_string(g.order) + "\t" + std::to_string(g.walk) + "\n";
  return o;
}
static void groups_load(const std::string &blob, const std::string &ck, uint32_t now) {
  size_t nl = blob.find('\n');
  if (nl == std::string::npos || blob.substr(0, nl) != std::to_string(fnv1a("v2|" + ck))) return;
  size_t pos = nl + 1;
  while (pos < blob.size()) {
    size_t end = blob.find('\n', pos);
    if (end == std::string::npos) break;
    std::vector<std::string> f;
    size_t a = pos;
    for (size_t i = pos; i <= end; i++)
      if (i == end || blob[i] == '\t') { f.push_back(blob.substr(a, i - a)); a = i + 1; }
    if (f.size() == 7) groups().push_back({f[0], f[1], f[2], f[3], f[4] == "1", atoi(f[5].c_str()), atoi(f[6].c_str()), now});
    pos = end + 1;
  }
}

static void build_rows(Frame &fr, const Look &L, uint32_t now) {
  fr.rows.clear();
  auto &G = groups();
  static std::string cfg_key;
  static bool loaded = false;
  std::string ck = L.points + "|" + L.dest_filter + "|" + L.aliases + (L.pin_train ? "T" : "t");
  if (!now) return;
  if (ck != cfg_key) {
    G.clear();
    cfg_key = ck;
    if (!loaded) { groups_load(groups_boot_blob(), ck, now); loaded = true; }  // rows survive reboots
  }
  size_t before = G.size();
  std::vector<Row> cur;
  auto find = [&](const std::string &key) -> Row * {
    for (auto &r : cur)
      if (r.key == key) return &r;
    return nullptr;
  };
  auto add = [&](const Departure &d, bool train, bool stale) {
    if (!dest_allowed(L, d.line, d.dest)) return;
    uint32_t when = d.when + (train ? d.delay_s : 0);
    int64_t secs = (int64_t) when - (int64_t) now;
    if (secs < -30) return;                                     // ghost / already gone
    int mins = secs > 0 ? (int) (secs / 60) : 0;
    int walk = train ? L.walk_train_min : stop_walk(L, d.point);
    std::string dest = short_dest(d.dest, L.aliases);
    // One row per line and platform (a platform serves one direction), like STIB stop displays;
    // the destination shown is the next vehicle's (short workings, depot runs without a name).
    std::string key = train ? std::string("~train") : d.line + "|" + d.point;
    Row *r = find(key);
    if (!r) {
      Row n;
      n.key = key; n.point = train ? "" : d.point; n.line = d.line; n.dest = dest; n.train = train;
      n.walk = walk; n.stale = stale;
      n.order = train ? 1000 : point_order(L, d.point);
      cur.push_back(n);
      r = &cur.back();
    }
    // The row exists as soon as the line is reported (rare lines keep their place even when the
    // only vehicle is already too close to catch); uncatchable departures are not shown.
    if (walk > 0 && mins < walk - 1) {
      if (r->missed < 0) r->missed = mins;
      return;
    }
    if (mins > L.horizon_min) {
      if (!r->next_epoch) r->next_epoch = when;
      return;
    }
    if (r->mins.empty()) {  // the earliest departure defines what the row shows
      r->line = d.line; r->walk = walk;
      if (!dest.empty()) r->dest = dest;
      r->delay_min = train ? d.delay_s / 60 : 0;
      r->plan_epoch = train ? d.when : 0;
      r->canceled = d.canceled;
    }
    if (r->mins.size() < 3) r->mins.push_back(mins);
  };
  for (auto &d : fr.m.deps) add(d, false, fr.stib_stale);    // sorted by time
  for (auto &d : fr.m.trains) add(d, true, fr.train_stale);  // sorted by time
  // remember groups (so a line keeps its row overnight), forget after 24 h unseen
  for (auto &r : cur) {
    std::sort(r.mins.begin(), r.mins.end());
    bool known = false;
    for (auto &g : G)
      if (g.key == r.key) {
        if (r.dest.empty()) r.dest = g.dest;  // depot runs etc.: keep the last known direction name
        g.seen = now; g.order = r.order; g.line = r.line; g.walk = r.walk;
        if (!r.dest.empty()) g.dest = r.dest;
        known = true;
      }
    if (!known) G.push_back({r.key, r.point, r.line, r.dest, r.train, r.order, r.walk, now});
  }
  G.erase(std::remove_if(G.begin(), G.end(), [&](const GroupMem &g) { return now - g.seen > 86400; }), G.end());
  if (G.size() != before && groups_saver()) groups_saver()(groups_serialize(ck));
  std::stable_sort(G.begin(), G.end(), [](const GroupMem &a, const GroupMem &b) {
    return a.order != b.order ? a.order < b.order : a.dest < b.dest;
  });
  for (auto &g : G) {
    Row *r = find(g.key);
    if (g.train && !L.pin_train && (!r || r->mins.empty())) continue;  // "Zug immer anzeigen" off
    if (r) { fr.rows.push_back(*r); continue; }
    Row e;
    e.key = g.key; e.point = g.point; e.line = g.line; e.dest = g.dest; e.train = g.train; e.walk = g.walk;
    e.order = g.order;
    e.stale = g.train ? fr.train_stale : fr.stib_stale;
    fr.rows.push_back(e);
  }
}

// Which rows are on screen: first (slots-1) fixed, the last slot rotates through the rest.
// Returns the indexes and how many rotate (for the page dots).
static std::vector<size_t> visible_rows(const Frame &fr, size_t slots, const Look &L, size_t &rot_n, size_t &rot_i) {
  std::vector<size_t> v;
  rot_n = rot_i = 0;
  size_t n = fr.rows.size();
  if (n <= slots) {
    for (size_t i = 0; i < n; i++) v.push_back(i);
    return v;
  }
  for (size_t i = 0; i + 1 < slots; i++) v.push_back(i);
  rot_n = n - (slots - 1);
  rot_i = (esphome::millis() / (uint32_t) (std::max(3, L.dwell_s) * 1000)) % rot_n;
  v.push_back(slots - 1 + rot_i);
  return v;
}

static std::string hhmm(uint32_t epoch) {
  time_t t = epoch;
  struct tm lt;
  localtime_r(&t, &lt);
  char b[8];
  snprintf(b, sizeof(b), "%02d:%02d", lt.tm_hour, lt.tm_min);
  return b;
}

// Text for a row without a catchable departure: grey minutes of a vehicle that is reported
// but too close to reach, else the next time beyond the preview, else a dash.
static std::string empty_text(const Row &r) {
  if (r.missed >= 0) return std::to_string(r.missed) + "'";
  return r.next_epoch ? hhmm(r.next_epoch) : std::string("-");
}

static void build_pager(Frame &fr, const Look &L, const Fonts &F, uint32_t now) {
  const Strings &s = S(L.ui_lang);
  const Model &m = fr.m;
  auto &v = fr.pager;
  v.clear();
  for (auto &a : m.alerts)
    if (a.source == 0 && (!a.expires || !now || a.expires > now)) v.push_back({TAG_DISR, a.text, 1, "d:" + a.text, 0});
  for (auto &c : m.cards)
    if (!c.expires || !now || c.expires > now) v.push_back({c.tag, c.text, c.prio, "c:" + c.key, 0});
  for (auto &c : ha_cards())  // JSON cards in the pager zone (p3 / z l)
    if (card_zone(c) == 'l') v.push_back({(uint8_t) (c.tag >= K_CAL ? c.tag - K_CAL : TAG_HA), card_line(c), c.p, "j:" + c.id, 0});
    else if (c.t == T_AGENDA && !c.rows.empty()) {  // the agenda also runs in the info line
      std::string a = c.ti.empty() ? std::string() : c.ti + ": ";
      for (size_t i = 0; i < c.rows.size(); i++)
        a += (i ? " · " : "") + (c.rows[i].val.empty() ? c.rows[i].label : c.rows[i].val + " " + c.rows[i].label);
      v.push_back({TAG_CAL, a, 2, "ja:" + c.id, 0});
    }
  bool wx_ok = m.wx.valid && !stale_src(m, SRC_WX, now, 3 * 3600);
  if (wx_ok && m.wx.warning_level == 1) v.push_back({TAG_WX, std::string(s.kmi) + ": " + m.wx.warning, 2, "w:warn", 0});
  if (wx_ok && m.wx.rain_start) {
    // KMI radar nowcast (10-min resolution): "Regen ab 22:40 (leicht), bis ca. 23:30"
    auto hm = [](uint32_t e) {
      time_t t = e;
      struct tm lt;
      localtime_r(&t, &lt);
      char b[8];
      snprintf(b, sizeof(b), "%02d:%02d", lt.tm_hour, lt.tm_min);
      return std::string(b);
    };
    const char *intensity = m.wx.rain_peak >= 1.0f ? s.heavy : m.wx.rain_peak >= 0.3f ? s.moderate : s.light;
    char b[96], e[32];
    if (m.wx.raining_now || (now && m.wx.rain_start <= now)) snprintf(b, sizeof(b), "%s (%s)", s.rain_now, intensity);
    else {
      char f[32];
      snprintf(f, sizeof(f), s.rain_from, hm(m.wx.rain_start).c_str());
      snprintf(b, sizeof(b), "%s (%s)", f, intensity);
    }
    std::string text = b;
    if (m.wx.rain_end) { snprintf(e, sizeof(e), s.rain_until, hm(m.wx.rain_end).c_str()); text += ", " + std::string(e); }
    v.push_back({TAG_WX, text, (uint8_t) (m.wx.raining_now ? 1 : 2), "w:rain", 0});
  } else if (wx_ok && m.wx.rain_in_h >= 1 && m.wx.rain_in_h <= 3) {
    char b[48];
    snprintf(b, sizeof(b), s.rain_in, m.wx.rain_in_h);  // beyond the radar window: hourly forecast
    v.push_back({TAG_WX, b, 2, "w:rain", 0});
  }
  if (m.commute_dep && now && m.commute_dep > now && !stale_src(m, SRC_COMMUTE, now, 1200)) {
    char b[64];
    int total = (int) ((m.commute_dep - now) + m.commute_dur_s) / 60;
    snprintf(b, sizeof(b), "%s: %d min (%s)", s.work, total, s.train);
    v.push_back({TAG_COMMUTE, b, 2, "pt", 0});
  }
  if (L.free_on && !L.free_text.empty()) v.push_back({TAG_HA, led_safe(L.free_text), 3, "free", 0});
  // headlines: 4 per cycle from the interleaved sources, rotating every 5 min
  if (!m.news.empty()) {
    size_t base = (now / 300) % m.news.size();
    for (size_t i = 0; i < std::min<size_t>(4, m.news.size()); i++) {
      const std::string &n = m.news[(base + i) % m.news.size()];
      v.push_back({TAG_NEWS, n, 3, "n:" + n, 0});
    }
  }
  std::stable_sort(v.begin(), v.end(), [](const PagerItem &a, const PagerItem &b) { return a.prio < b.prio; });
  for (auto &p : v) p.width = text_w(F.small, p.text);
}

// Word-wrap into lines of max_w px (long single words are split by characters).
static void wrap(const Fonts &F, Font *f, const std::string &body, int max_w, std::vector<std::string> &out) {
  out.clear();
  std::string cur, word;
  auto push_word = [&]() {
    if (word.empty()) return;
    while (text_w(f, word) > max_w) {  // hard split very long words
      size_t n = utf8_chars(word), k = n;
      while (k > 1 && text_w(f, utf8_sub(word, 0, k)) > max_w) k--;
      if (!cur.empty()) { out.push_back(cur); cur.clear(); }
      out.push_back(utf8_sub(word, 0, k));
      word = utf8_sub(word, k, n - k);
    }
    std::string cand = cur.empty() ? word : cur + " " + word;
    if (text_w(f, cand) > max_w && !cur.empty()) { out.push_back(cur); cur = word; }
    else cur = cand;
    word.clear();
  };
  for (char ch : body) {
    if (ch == ' ' || ch == '\n' || ch == '\r') push_word();
    else word += ch;
  }
  push_word();
  if (!cur.empty()) out.push_back(cur);
}

// Rebuild the cached frame when the model / look changed, or once per second.
static void refresh_frame(const Fonts &F, const Look &L, uint32_t now) {
  Frame &fr = frame();
  uint32_t g = gen();
  uint32_t sec = esphome::millis() / 1000;
  bool model_changed = g != fr.model_gen;
  if (!model_changed && L.version == fr.look_ver && sec == fr.built_s) return;
  if (model_changed) { fr.m = snapshot(); fr.model_gen = g; }
  fr.look_ver = L.version;
  fr.built_s = sec;
  const Strings &s = S(L.ui_lang);
  fr.stib_stale = stale_src(fr.m, SRC_STIB, now, 180);
  fr.train_stale = stale_src(fr.m, SRC_TRAIN, now, 300);
  fr.any_data = fr.m.ts[SRC_STIB] || fr.m.ts[SRC_TRAIN];
  // visible rows (same geometry as render()): a pinned train must land in a visible slot
  int vy0 = L.status_bar ? 11 : 0, vbottom = L.pager ? 53 : 64;
  (void) vy0; (void) vbottom;
  build_rows(fr, L, now);
  build_pager(fr, L, F, now);
  // P0 takeover: BE-Alert, HA critical, or KMI orange/red (fresh data only)
  std::string title, body;
  for (auto &a : fr.m.alerts) {
    if ((a.source == 1 || a.source == 3) && (!a.expires || !now || a.expires > now)) {
      title = a.source == 1 ? s.bealert : s.alert;
      body = a.text;
      break;
    }
  }
  if (body.empty() && fr.m.wx.valid && fr.m.wx.warning_level >= 2 && !stale_src(fr.m, SRC_WX, now, 3 * 900)) {
    title = std::string(s.kmi) + " " + s.alert;
    body = fr.m.wx.warning;
  }
  if (body != fr.p0_body) { fr.p0_body = body; wrap(F, F.mid, body, 188, fr.p0_lines); }
  fr.p0_title = title;
}

// ------------------------------------------------------------------ drawing pieces
static Color minute_color(int m, const Row &r, const Look &L) {
  if (r.stale) return C_SEC;
  return (m <= r.walk) ? C_LEAVE : C_CATCH;
}

// Walking time (iteration 6): pedestrian glyph + minutes, dim, right-aligned at x_right. Returns width.
static int walk_tag(Display &it, const Fonts &F, int x_right, int y, int walk) {
  std::string t = std::to_string(walk);
  int tw = text_w(F.small, t);
  txt(it, F, F.small, x_right, y + 4, t, C_SEC, 2);
  static const Color C_WALK(0x9A, 0x94, 0x8C);  // a bit brighter than C_SEC: 5x7 glyph must survive dimming
  icon(it, x_right - tw - 6, y + 3, "walk", 7, &C_WALK);
  return tw + 6;
}

// Standard row, 14 px: badge 22x12 | destination 6x10 | walk | first dep 9x15B right at 168 | second 191.
static void dep_row(Display &it, const Fonts &F, int y, const Row &r, const Look &L) {
  badge(it, F, 1, y + 1, r.line);
  if (r.mins.empty()) {  // fixed row without a departure in the preview: next time or dash
    std::string t = empty_text(r);
    txt(it, F, F.mid, 172, y + 4, t, C_SEC, 2);
    int mw = text_w(F.mid, t) + 4;
    int wt = L.show_walk ? walk_tag(it, F, 172 - mw - 2, y, r.walk) : 0;
    txt(it, F, F.mid, 27, y + 4, fit_words(F.mid, r.dest, 172 - mw - wt - 8 - 27), C_SEC);
    return;
  }
  int m0 = r.mins[0];
  Color c0 = minute_color(m0, r, L);
  int mw;
  if (r.canceled) {
    txt(it, F, F.mid, 168, y + 3, "X", C_LEAVE, 2);
    mw = 8;
  } else if (m0 <= 0) {
    arrows_now(it, 168, y + 1, c0);
    mw = 16;
  } else {
    std::string ms = std::to_string(m0);
    txt(it, F, F.big, 168, y + 2, ms, c0, 2);
    txt(it, F, F.small, 169, y + 2, "'", c0);
    mw = text_w(F.big, ms);
  }
  if (r.train && r.delay_min > 0) txt(it, F, F.small, 191, y + 4, "+" + std::to_string(r.delay_min), C_LEAVE, 2);
  else if (L.second && r.mins.size() > 1) txt(it, F, F.small, 191, y + 4, std::to_string(r.mins[1]) + "'", C_SEC, 2);
  int wt = L.show_walk ? walk_tag(it, F, 168 - mw - 5, y, r.walk) : 0;
  int dw = std::min(116, 168 - mw - 5 - wt - 4 - 27);
  std::string n = fit_words(F.mid, r.dest, dw);
  Color dc = r.canceled ? C_SEC : C_WARM;
  if (!n.empty()) {
    txt(it, F, F.mid, 27, y + 4, n, dc);
  } else {
    std::string sm = fit_words(F.small, r.dest, dw);
    txt(it, F, F.small, 27, y + 5, sm.empty() ? utf8_sub(r.dest, 0, dw / 5) : sm, dc);
  }
}

// Compact row, 10 px: badge 19x9 (5x7) | destination 5x7 | first dep 6x10 right at 172 | second 191.
static void dep_row_compact(Display &it, const Fonts &F, int y, const Row &r, const Look &L) {
  badge(it, F, 1, y, r.line, 19, 9, F.small);
  bool empty = r.mins.empty();
  int m0 = empty ? 0 : r.mins[0];
  Color c0 = empty ? C_SEC : minute_color(m0, r, L);
  std::string ms = empty ? (empty_text(r))
                         : r.canceled ? "X" : (m0 <= 0 ? "0" : std::to_string(m0)) + "'";
  txt(it, F, F.mid, 172, y + 1, ms, (!empty && r.canceled) ? C_LEAVE : c0, 2);
  if (!empty && r.train && r.delay_min > 0) txt(it, F, F.small, 191, y + 2, "+" + std::to_string(r.delay_min), C_LEAVE, 2);
  else if (!empty && L.second && r.mins.size() > 1) txt(it, F, F.small, 191, y + 2, std::to_string(r.mins[1]) + "'", C_SEC, 2);
  int wt = L.show_walk ? walk_tag(it, F, 172 - text_w(F.mid, ms) - 4, y - 2, r.walk) : 0;
  int dw = 172 - text_w(F.mid, ms) - wt - 23 - 6;
  std::string n = fit_words(F.small, r.dest, dw);
  txt(it, F, F.small, 23, y + 2, n.empty() ? utf8_sub(r.dest, 0, dw / 5) : n, r.canceled ? C_SEC : C_WARM);
}

static void status_bar(Display &it, const Fonts &F, const Model &m, const Look &L, const esphome::ESPTime &t,
                       bool alert_dot, uint32_t now) {
  const Strings &s = S(L.ui_lang);
  char buf[32];
  if (t.is_valid()) {
    snprintf(buf, sizeof(buf), "%02d:%02d", t.hour, t.minute);
    txt(it, F, F.mid, 1, 2, buf, C_WARM);
    snprintf(buf, sizeof(buf), "%s %d.%d.", s.wd[t.day_of_week - 1], t.day_of_month, t.month);
    txt(it, F, F.small, 36, 3, buf, C_SEC);
  } else {
    txt(it, F, F.mid, 1, 2, "--:--", C_SEC);
  }
  if (alert_dot) it.filled_rectangle(95, 3, 3, 3, C_LEAVE);
  if (m.wx.valid && !stale_src(m, SRC_WX, now, 3600)) {  // mockup: icon x=150, range right-aligned at 140
    snprintf(buf, sizeof(buf), "%d°", m.wx.temp);
    txt(it, F, F.mid, 191, 2, buf, C_WARM, 2);
    int ix = std::min(150, 191 - text_w(F.mid, buf) - 12);  // never touching the temperature
    icon(it, ix, 1, ww_condition(m.wx.ww, m.wx.night), 9);
    if (m.wx.has_min && m.wx.has_max) {
      if (m.wx.tmin < 0) snprintf(buf, sizeof(buf), "%d / %d°", m.wx.tmin, m.wx.tmax);
      else snprintf(buf, sizeof(buf), "%d-%d°", m.wx.tmin, m.wx.tmax);
      txt(it, F, F.small, ix - 4, 3, buf, C_SEC, 2);
    }
  }
}

// Pager: remembers the shown item by key (stable when the list changes), scrolls long text once
// L.scroll_px px per frame (20/40/60 px/s at the 50 ms render tick) after 1.5 s, then holds.
// Frame-counted, so every step is the same size (time-based offsets gave uneven jumps = judder). Draws only the visible characters (fixed 5 px font).
static void pager(Display &it, const Fonts &F, const std::vector<PagerItem> &items, const Look &L, int y,
                  int avail = 185) {
  static std::string cur_key;
  static uint32_t started = 0, frame_no = 0, start_frame = 0;
  frame_no++;
  if (items.empty()) { cur_key.clear(); return; }
  uint32_t ms = esphome::millis();
  size_t idx = 0;
  bool found = false;
  for (size_t i = 0; i < items.size(); i++)
    if (items[i].key == cur_key) { idx = i; found = true; break; }
  if (!found) { cur_key = items[0].key; idx = 0; started = ms; start_frame = frame_no; }
  const PagerItem *p = &items[idx];
  int over = p->width - avail;
  uint32_t need = L.dwell_s * 1000 + (over > 0 ? over * 50 / std::max(1, L.scroll_px) + 2000 : 0);
  if (ms - started > need) {
    idx = (idx + 1) % items.size();
    p = &items[idx];
    cur_key = p->key;
    started = ms;
    start_frame = frame_no;
    over = p->width - avail;
  }
  it.filled_rectangle(1, y + 1, 2, 6, tag_color(p->tag));   // category tag (colour = topic)
  int el = (int) (frame_no - start_frame) - 30;  // 30 frames = 1.5 s hold before scrolling
  int off = (over > 0 && el > 0) ? std::min(over, el * std::max(1, L.scroll_px)) : 0;
  size_t first = off / 5;  // misc-fixed 5x7: 5 px per character
  std::string vis = utf8_sub(p->text, first, avail / 5 + 2);
  it.start_clipping(esphome::display::Rect(6, y, avail, 9));
  txt(it, F, F.small, 6 - (off % 5), y + 1, vis, Color(0xB0, 0xA9, 0x9E));
  it.end_clipping();
}

static void takeover(Display &it, const Fonts &F, const Frame &fr, const esphome::ESPTime &t, uint32_t since_ms) {
  it.filled_rectangle(0, 0, 192, 14, Color(0xB0, 0, 0));
  Color w(255, 255, 255);
  icon(it, 2, 3, "warn", 7, &w);
  txt(it, F, F.mid, 14, 3, fr.p0_title, w);
  if (t.is_valid()) {
    char b[8];
    snprintf(b, sizeof(b), "%02d:%02d", t.hour, t.minute);
    txt(it, F, F.small, 190, 4, b, Color(255, 200, 200), 2);
  }
  // mockup P0: 3 lines at y = 19 / 31 / 43, page indicator at y = 56
  int pages = std::max<int>(1, (fr.p0_lines.size() + 2) / 3);
  int pg = ((esphome::millis() - since_ms) / 5000) % pages;
  for (int i = 0; i < 3; i++) {
    size_t li = pg * 3 + i;
    if (li < fr.p0_lines.size()) txt(it, F, F.mid, 2, 19 + i * 12, fr.p0_lines[li], C_WARM);
  }
  if (pages > 1) {
    char b[8];
    snprintf(b, sizeof(b), "%d/%d", pg + 1, pages);
    txt(it, F, F.small, 190, 56, b, C_SEC, 2);
  }
}

static void night_screen(Display &it, const Fonts &F, const Frame &fr, const Look &L, const esphome::ESPTime &t) {
  if (L.night == NIGHT_DARK) return;
  char b[16];
  if (t.is_valid()) {
    snprintf(b, sizeof(b), "%02d:%02d", t.hour, t.minute);
    int shift = (t.minute / 10) % 3 - 1;  // anti burn-in: move 1 px every 10 min
    txt(it, F, F.clock, 96 + shift, 6, b, C_NIGHT, 1);
  }
  if (L.night == NIGHT_CLOCK) return;
  if (fr.m.wx.valid) {
    icon(it, 60, 30, ww_condition(fr.m.wx.ww, true), 9, &C_NIGHT2);
    snprintf(b, sizeof(b), "%d°", fr.m.wx.temp);
    txt(it, F, F.mid, 72, 31, b, C_NIGHT2);
  }
  const Row *nr = nullptr;
  for (auto &r : fr.rows)
    if (!r.mins.empty() && (!nr || r.mins[0] < nr->mins[0])) nr = &r;
  if (nr) {
    const Row &r = *nr;
    badge(it, F, 100, 30, r.line, 21, 10, F.small, true);
    txt(it, F, F.mid, 140, 32, std::to_string(std::max(0, r.mins[0])) + "'", C_NIGHT, 2);
  }
}



// Delay (trains only - STIB real-time minutes already include delays): red "+N'" like on SNCB
// departure boards, the same in every layout.
static const Color C_DELAY_BG(0xC8, 0x1E, 0x14);
static const Color C_SNCB_BG(0x0A, 0x1E, 0x46);  // SNCB departure-board navy (train rows/cells)
static int delay_chip(Display &it, const Fonts &F, int x_right, int y, int delay_min) {
  std::string d = "+" + std::to_string(delay_min) + "'";
  txt(it, F, F.small, x_right, y, d, C_LEAVE, 2);
  return text_w(F.small, d);
}

// Trains to Brussels Airport get the airport pictogram (as on SNCB boards).
static bool airport_dest(const std::string &d) {
  std::string l = d;
  for (auto &ch : l) ch = (char) tolower((unsigned char) ch);
  for (const char *k : {"airport", "aéroport", "aeroport", "luchthaven", "flughafen", "zaventem"})
    if (l.find(k) != std::string::npos) return true;
  return false;
}

// Destination; trains get their scheduled time after it in grey (SNCB boards show both).
static void dest_txt(Display &it, const Fonts &F, Font *f, int x, int y, const Row &r, int maxw, Color c) {
  std::string plan = (r.train && r.plan_epoch) ? hhmm(r.plan_epoch) : std::string();
  bool air = r.train && airport_dest(r.dest);
  int ch = cap_h(f, F);
  if (r.train && look().sncb_logo && maxw > 30) {  // SNCB "B" in a blue oval (12x9), white B
    static const char *const OV[9] = {"..########..", ".##########.", "############", "############", "############",
                                      "############", "############", ".##########.", "..########.."};
    static const char *const BB[7] = {"###.", "#..#", "#..#", "###.", "#..#", "#..#", "###."};
    int ly = y + ch / 2 - 4;
    for (int j = 0; j < 9; j++)
      for (int i = 0; i < 12; i++)
        if (OV[j][i] == '#') it.draw_pixel_at(x + i, ly + j, Color(0x01, 0x6A, 0xB3));
    for (int j = 0; j < 7; j++)
      for (int i = 0; i < 4; i++)
        if (BB[j][i] == '#') it.draw_pixel_at(x + 4 + i, ly + 1 + j, Color(255, 255, 255));
    x += 15;
    maxw -= 15;
  }
  Font *pf = f == F.tiny ? F.tiny : F.small;
  int aw = air ? 8 : 0;
  int pw = plan.empty() ? 0 : text_w(pf, plan) + 4;
  std::string d = fit_words(f, r.dest, maxw - pw - aw);
  if (d.empty()) { d = fit_words(f, r.dest, maxw - aw); pw = 0; }
  if (d.empty() && f != F.tiny) { f = F.small; d = fit_words(f, r.dest, maxw - aw); }
  txt(it, F, f, x, y, d, c);
  int xe = x + text_w(f, d);
  ch = cap_h(f, F);
  static const Color C_PLANE(0x41, 0x9B, 0xF5);  // airport pictogram in blue
  if (air) { icon(it, xe + 3, y + ch - 7, "plane", 7, &C_PLANE); xe += aw; }
  if (pw) txt(it, F, pf, xe + 4, y + ch - cap_h(pf, F), plan, C_SEC);
}

// ------------------------------------------------------------------ iteration 8 layouts
static const Color C_WALK(0x9A, 0x94, 0x8C);

// pedestrian glyph + minutes at a FIXED column (left aligned), only when the walk is > 1 min
static void walk_fixed(Display &it, const Fonts &F, int x, int y, int walk) {
  if (walk <= 1) return;
  icon(it, x, y, "walk", 7, &C_WALK);
  txt(it, F, F.small, x + 7, y + 1, std::to_string(walk), C_SEC);
}

// minutes (or arrows / X / HH:MM / dash) right-aligned at x_right; second value right at x2
static void minutes_cell(Display &it, const Fonts &F, const Row &r, const Look &L, int x_right, int y, int x2,
                         Font *big) {
  if (r.mins.empty()) {
    txt(it, F, F.mid, x2, y + 2, empty_text(r), C_SEC, 2);
    return;
  }
  int m0 = r.mins[0];
  Color c = minute_color(m0, r, L);
  if (r.canceled) txt(it, F, F.mid, x_right, y + 2, "X", C_LEAVE, 2);
  else if (m0 <= 0) arrows_now(it, x_right, y, c);
  else {
    txt(it, F, big, x_right, y, std::to_string(m0), c, 2);
    txt(it, F, F.small, x_right + 1, y, "'", c);
  }
  if (r.train && r.delay_min > 0) delay_chip(it, F, x2, y + 3, r.delay_min);
  else if (L.second && r.mins.size() > 1) txt(it, F, F.small, x2, y + 3, std::to_string(r.mins[1]) + "'", C_SEC, 2);
}

// Slim status (9 px) for the 4-row layout: clock, date, weather icon always, temperature + range.
static void status_slim(Display &it, const Fonts &F, const Model &m, const Look &L, const esphome::ESPTime &t,
                        bool alert_dot, uint32_t now) {
  const Strings &s = S(L.ui_lang);
  char buf[32];
  if (t.is_valid()) {
    snprintf(buf, sizeof(buf), "%02d:%02d", t.hour, t.minute);
    txt(it, F, F.small, 1, 1, buf, C_WARM);
    snprintf(buf, sizeof(buf), "%s %d.%d.", s.wd[t.day_of_week - 1], t.day_of_month, t.month);
    txt(it, F, F.small, 34, 1, buf, C_SEC);
  }
  if (alert_dot) it.filled_rectangle(95, 2, 3, 3, C_LEAVE);
  if (m.wx.valid && !stale_src(m, SRC_WX, now, 3600)) {
    if (m.wx.has_min && m.wx.has_max) snprintf(buf, sizeof(buf), "%d°  %d/%d°", m.wx.temp, m.wx.tmin, m.wx.tmax);
    else snprintf(buf, sizeof(buf), "%d°", m.wx.temp);
    txt(it, F, F.small, 191, 1, buf, C_WARM, 2);
    icon(it, 191 - text_w(F.small, buf) - 12, 0, ww_condition(m.wx.ww, m.wx.night), 9);  // 3 px gap
  }
}

// FOUR: 4 equal rows (11 px with status bar + pager, 12 px when there is room), every group
// with its destination. Trains look exactly like STIB rows; only the badge is SNCB style.
static void layout_four(Display &it, const Fonts &F, const Frame &fr, const Look &L, int y0) {
  int bottom = L.pager ? 55 : 64;
  int pitch = (bottom - y0) / 4 >= 12 ? 12 : 11;
  size_t n = std::min<size_t>(fr.rows.size(), std::max(0, (bottom - y0) / pitch));
  for (size_t i = 0; i < n; i++) {
    const Row &r = fr.rows[i];
    int y = y0 + i * pitch;
    badge(it, F, 1, y + 1, r.line, 22, 10);
    if (L.show_walk) walk_fixed(it, F, 124, y + 2, r.walk);
    minutes_cell(it, F, r, L, 166, y + 1, 191, F.big);
    int dw = (L.show_walk && r.walk > 1 ? 124 : 140) - 27 - 3;
    dest_txt(it, F, F.mid, 27, y + 3, r, dw, r.canceled ? C_SEC : C_WARM);
  }
}


// Compact cell: badge 18 | destination (4x6) | walk (glyph + 4x6) | minutes 9x15B | [delay].
static void split_cell(Display &it, const Fonts &F, const Row &r, const Look &L, int x0, int x1, int y) {
  badge(it, F, x0, y + 1, r.line, 18, 12);
  int right = x1;
  int mr;
  if (r.mins.empty()) {
    std::string t = empty_text(r);
    txt(it, F, F.mid, right, y + 4, t, C_SEC, 2);
    mr = right - text_w(F.mid, t) - 1;
  } else {
    if (r.train && r.delay_min > 0) right -= delay_chip(it, F, x1, y + 4, r.delay_min) + 2;
    int m0 = r.mins[0];
    Color c = minute_color(m0, r, L);
    int xr = right - 3;
    if (r.canceled) { txt(it, F, F.mid, xr, y + 3, "X", C_LEAVE, 2); mr = xr - 8; }
    else if (m0 <= 0) { arrows_now(it, xr, y + 1, c); mr = xr - 16; }
    else {
      std::string ms = std::to_string(m0);
      txt(it, F, F.big, xr, y + 1, ms, c, 2);
      txt(it, F, F.small, xr + 1, y + 1, "'", c);
      mr = xr - text_w(F.big, ms);
    }
  }
  int wx = mr - 3;
  if (L.show_walk && r.walk > 1) {
    std::string wt = std::to_string(r.walk);
    wx = mr - 3 - (6 + text_w(F.tiny, wt));
    icon(it, wx, y + 3, "walk", 7, &C_WALK);
    txt(it, F, F.tiny, wx + 6, y + 4, wt, C_SEC);
  }
  int dw = wx - (x0 + 21) - 1;
  if (dw > 8) {
    if (fit_words(F.tiny, r.dest, dw).empty()) txt(it, F, F.tiny, x0 + 21, y + 4, utf8_sub(r.dest, 0, dw / 4), C_WARM);
    else dest_txt(it, F, F.tiny, x0 + 21, y + 4, r, dw, C_WARM);
  }
}

// PREMIUM: first two groups as large rows (9x15 destinations), next two side by side.
static void layout_premium(Display &it, const Fonts &F, const Frame &fr, const Look &L, int y0) {
  size_t i = 0;
  for (; i < fr.rows.size() && i < 2; i++) {
    const Row &r = fr.rows[i];
    int y = y0 + i * 14;
    badge(it, F, 1, y + 1, r.line);
    bool w = L.show_walk && r.walk > 1;
    if (w) walk_fixed(it, F, 122, y + 3, r.walk);
    minutes_cell(it, F, r, L, 166, y + 1, 191, F.big);
    int dw = (w ? 122 : 138) - 29 - 3;
    Color dc = r.canceled ? C_SEC : C_WARM;
    if (!fit_words(F.dest, r.dest, dw).empty()) dest_txt(it, F, F.dest, 29, y + 1, r, dw, dc);
    else dest_txt(it, F, F.mid, 29, y + 3, r, dw, dc);
  }
  // split row (iteration 9): next two groups side by side, each with a compact destination;
  // trains look like STIB cells; only the badge is SNCB style.
  int y = y0 + 30;
  const int cells[2][2] = {{1, 82}, {88, 191}};
  for (size_t k = 0; k < 2 && i < fr.rows.size(); k++, i++)
    split_cell(it, F, fr.rows[i], L, cells[k][0], cells[k][1], y);
}

// HERO: two very large rows (10x20 minutes) for single-stop users.
static void layout_hero(Display &it, const Fonts &F, const Frame &fr, const Look &L, int y0) {
  for (size_t k = 0; k < fr.rows.size() && k < 2; k++) {
    const Row &r = fr.rows[k];
    int y = y0 + 1 + k * 21;
    badge(it, F, 1, y + 2, r.line, 24, 14);
    bool w = L.show_walk && r.walk > 1;
    if (w) walk_fixed(it, F, 112, y + 6, r.walk);
    if (r.mins.empty()) {
      txt(it, F, F.mid, 191, y + 6, empty_text(r), C_SEC, 2);
    } else {
      Color c = minute_color(r.mins[0], r, L);
      if (r.canceled) txt(it, F, F.clock, 166, y + 3, "X", C_LEAVE, 2);
      else if (r.mins[0] <= 0) arrows_now(it, 166, y + 4, c);
      else {
        txt(it, F, F.clock, 166, y + 3, std::to_string(r.mins[0]), c, 2);
        txt(it, F, F.mid, 167, y + 3, "'", c);
      }
      if (r.train && r.delay_min > 0) delay_chip(it, F, 191, y + 8, r.delay_min);
      else if (L.second && r.mins.size() > 1) txt(it, F, F.small, 191, y + 8, std::to_string(r.mins[1]) + "'", C_SEC, 2);
    }
    dest_txt(it, F, F.mid, 29, y + 6, r, (w ? 112 : 128) - 29 - 3, r.canceled ? C_SEC : C_WARM);
  }
}

inline bool in_night(const Look &L, const esphome::ESPTime &t) {
  if (L.night == NIGHT_OFF || !t.is_valid() || L.night_from == L.night_to) return false;
  int mod = t.hour * 60 + t.minute;
  if (L.night_from < L.night_to) return mod >= L.night_from && mod < L.night_to;
  return mod >= L.night_from || mod < L.night_to;  // spans midnight
}

}  // namespace perron
#include "perron_cards_draw.h"
namespace perron {

// ------------------------------------------------------------------ main entry
static void render(Display &it, const Fonts &F, const Look &L, const esphome::ESPTime &t) {
  uint32_t now = now_epoch();
  refresh_frame(F, L, now);
  Frame &fr = frame();
  const Strings &s = S(L.ui_lang);

  // P0 takeover: full screen 20 s, then every 10 min for 8 s, until the alert is gone.
  static uint32_t p0_since = 0;
  static std::string p0_last;
  uint32_t ms = esphome::millis();
  if (!fr.p0_body.empty()) {
    if (fr.p0_body != p0_last) { p0_last = fr.p0_body; p0_since = ms; }
    uint32_t el = ms - p0_since;
    bool show = el < 20000 || ((el - 20000) % 600000) >= 592000;
    if (show) {
      uint32_t page_base = el < 20000 ? p0_since : ms - ((el - 20000) % 600000 - 592000);
      takeover(it, F, fr, t, page_base);
      return;
    }
  } else {
    p0_last.clear();
  }

  frame_no()++;  // drives text marquees (1 px per frame)
  // Home Assistant cards (JSON templates / canvas / images)
  static uint32_t last_exp_s = 0;
  if (ms / 1000 != last_exp_s) { last_exp_s = ms / 1000; expire_cards(now); }
  const bool night = in_night(L, t);
  CardView cv = pick_cards(fr, ms, night);
  if (cv.full) {
    if (!(cv.full->t == T_IMG && cv.full->fb)) status_bar(it, F, fr.m, L, t, false, now);
    card_full(it, F, *cv.full, ms);
    if (L.pager && !(cv.full->t == T_IMG && cv.full->fb)) pager(it, F, fr.pager, L, 55);  // news keep running
    return;
  }
  if (night) {
    night_screen(it, F, fr, L, t);
    return;
  }
  if (cv.panel) {
    panel_departures(it, F, fr, L, t);
    card_panel(it, F, *cv.panel, ms);
    if (L.pager) pager(it, F, fr.pager, L, 55, 120);
    return;
  }

  int y0 = 0;
  if (L.status_bar) {
    if (L.layout == LAYOUT_FOUR) { status_slim(it, F, fr.m, L, t, !fr.p0_body.empty(), now); y0 = 9; }
    else { status_bar(it, F, fr.m, L, t, !fr.p0_body.empty(), now); y0 = 11; }
  }
  const bool live = now && fr.any_data;

  if (L.layout == LAYOUT_PREMIUM) layout_premium(it, F, fr, L, y0);
  else if (L.layout == LAYOUT_FOUR) layout_four(it, F, fr, L, y0);
  else layout_hero(it, F, fr, L, y0);
  if (fr.rows.empty()) txt(it, F, F.mid, 96, y0 + 14, live ? s.no_deps : s.no_live, C_SEC, 1);
  if (L.pager) pager(it, F, fr.pager, L, L.layout == LAYOUT_FOUR ? 56 : L.layout == LAYOUT_PREMIUM ? 55 : 54);
}

}  // namespace perron
