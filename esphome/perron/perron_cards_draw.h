// Perron – Home Assistant cards v1: drawing + scheduling. Included by perron_render.h right
// before render(); mockups: tools/mockup/scenes_cards.py, spec: docs/cards.md.
//
// Full-screen frame: status bar stays (y0-9), body x1-190 / y11-55, footer y56-63 replaces the
// pager. Panel frame: card on panel 3 (x128-191), departures reflow to x0-126.
#pragma once

#include "perron_cards.h"

namespace perron {

static const Color C_FOOT(0xB0, 0xA9, 0x9E);
static const Color C_W2(0x80, 0x74, 0x66);
static const Color C_W4(0x40, 0x3A, 0x33);

static Color tokc(uint8_t k) {
  switch (k) {
    case K_W: return C_WARM;
    case K_S: return C_SEC;
    case K_A: return C_CATCH;
    case K_R: return C_LEAVE;
    case K_RC: return C_DELAY_BG;
    case K_NV: return C_SNCB_BG;
    case K_W2: return C_W2;
    case K_W4: return C_W4;
    default: return tag_color(k - K_CAL);  // same order as enum Tag
  }
}
static Font *fnt(const Fonts &F, uint8_t f) {
  switch (f) {
    case FT_TINY: return F.tiny;
    case FT_MID: return F.mid;
    case FT_DEST: return F.dest;
    case FT_BIG: return F.big;
    case FT_CLOCK: return F.clock;
    default: return F.small;
  }
}
static Color sev_color(const HaCard &c, Color info = C_WARM) {
  return c.s == 'a' ? C_CATCH : c.s == 'x' ? C_LEAVE : info;
}
// "left|right" convention for two-part secondary text
static void split2(const std::string &s, std::string &a, std::string &b) {
  size_t p = s.find('|');
  if (p == std::string::npos) { a = s; b.clear(); }
  else { a = s.substr(0, p); b = s.substr(p + 1); }
}
static bool numeric(const std::string &v) {
  if (v.empty() || v.size() > 5) return false;
  for (char c : v)
    if (!(isdigit((unsigned char) c) || c == '.' || c == ',' || c == '%' || c == '\'' || c == ':' || c == '-')) return false;
  return true;
}

static void draw_slot(Display &it, const std::string &key, int x, int y, int maxw, int maxh) {
  ImgSlot *s = slot(key, false);
  if (!s || !s->ready) return;
  it.start_clipping(esphome::display::Rect(x, y, maxw, maxh));
  if (s->url) {
    if (url_drawer()) url_drawer()(&it, s->url_fmt, x, y);
  } else if (s->px) {
    int w = std::min<int>(s->w, maxw), h = std::min<int>(s->h, maxh);
    for (int j = 0; j < h; j++) {
      const uint16_t *row = s->px + j * s->w;
      for (int i = 0; i < w; i++) {
        uint16_t c = row[i];
        if (!c) continue;
        uint8_t r = (c >> 11) & 0x1F, g = (c >> 5) & 0x3F, b = c & 0x1F;
        it.draw_pixel_at(x + i, y + j, Color((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)));
      }
    }
  }
  it.end_clipping();
}
static bool slot_ready(const std::string &key) {
  ImgSlot *s = slot(key, false);
  return s && s->ready;
}

// segmented progress bar: 3 px segments, 1 px gaps, track w:4, fill w
static void seg_bar(Display &it, int x0, int x1, int y, int h, int pct, Color fill = C_WARM) {
  int n = (x1 - x0 + 2) / 4;
  int lit = (n * std::max(0, pct) + 50) / 100;
  for (int k = 0; k < n; k++) it.filled_rectangle(x0 + k * 4, y, 3, h, k < lit ? fill : C_W4);
}

static void card_footer(Display &it, const Fonts &F, const HaCard &c, const std::string &meta) {
  it.filled_rectangle(1, 57, 2, 6, tokc(c.tag));
  int mw = meta.empty() ? 0 : text_w(F.small, meta) + 4;
  std::string cap = c.ft.empty() ? (c.t == T_MSG || c.t == T_PROG || c.t == T_RING ? "" : c.ti) : c.ft;
  txt(it, F, F.small, 6, 57, fit_words(F.small, cap, 185 - mw), C_FOOT);
  if (!meta.empty()) txt(it, F, F.small, 191, 57, meta, C_SEC, 2);
}

static void canvas(Display &it, const Fonts &F, const HaCard &c) {
  for (auto &e : c.el) {
    Color col = tokc(e.col);
    switch (e.t) {
      case 't': case 'n': {
        int maxw = (c.z == 'p' ? 191 : 191) - e.x;
        txt(it, F, fnt(F, e.font), e.x, e.y, fit_words(fnt(F, e.font), e.s, maxw), col);
        break;
      }
      case 'i': icon(it, e.x, e.y, e.s.c_str(), e.size, &col); break;
      case 'b': {
        int w = text_w(F.small, e.s) + 4;
        it.filled_rectangle(e.x, e.y, w, 9, col);
        txt(it, F, F.small, e.x + 2, e.y + 1, e.s, Color(255, 255, 255));
        break;
      }
      case 'r':
        if (e.fill) it.filled_rectangle(e.x, e.y, e.w, e.h, col);
        else it.rectangle(e.x, e.y, e.w, e.h, col);
        break;
      case 'g':
        it.filled_rectangle(e.x, e.y, e.w, e.h, C_W4);
        it.filled_rectangle(e.x, e.y, e.w * e.pct / 100, e.h, col);
        break;
      case 'm': draw_slot(it, e.s, e.x, e.y, 192 - e.x, 64 - e.y); break;
    }
  }
}

// ------------------------------------------------------------------ full-screen templates
static void card_full(Display &it, const Fonts &F, const HaCard &c, uint32_t ms) {
  std::string a, b, meta;
  Color hc = sev_color(c);
  if (c.s == 'x') it.horizontal_line(1, 10, 190, C_LEAVE);
  switch (c.t) {
    case T_HERO: {
      int x = 26;
      if (!c.ic.empty()) icon(it, 4, 14, c.ic.c_str(), 16, &hc);
      else x = 4;
      int vw = text_w(F.clock, c.val);
      txt(it, F, F.clock, x, 16, c.val, hc);
      if (!c.u.empty()) txt(it, F, F.mid, x + vw + 3, 22, c.u, C_SEC);
      txt(it, F, F.dest, x, 37, fit_words(F.dest, c.ti, 118 - x), C_WARM);
      split2(c.sub, a, b);
      txt(it, F, F.small, 190, 18, fit_words(F.small, a, 62), C_WARM, 2);
      txt(it, F, F.small, 190, 30, fit_words(F.small, b, 62), C_SEC, 2);
      break;
    }
    case T_PROG: {
      int x = 26;
      if (!c.ic.empty()) icon(it, 4, 13, c.ic.c_str(), 16, &C_WARM);
      else x = 4;
      int vw = text_w(F.big, c.val);
      txt(it, F, F.dest, x, 14, fit_words(F.dest, c.ti, 186 - vw - x - 6), hc);
      txt(it, F, F.big, 190, 13, c.val, C_WARM, 2);
      seg_bar(it, x, 190, 32, 4, c.pct);
      split2(c.sub, a, b);
      txt(it, F, F.small, x, 41, fit_words(F.small, a, 80), C_SEC);
      txt(it, F, F.small, 190, 41, fit_words(F.small, b, 80), C_WARM, 2);
      break;
    }
    case T_LIST: {
      bool dense = c.rows.size() > 3;
      int pitch = dense ? 11 : 14;
      for (size_t i = 0; i < c.rows.size(); i++) {
        const ListRow &r = c.rows[i];
        int y = 11 + i * pitch;
        Color vc = tokc(r.col);
        Color icc = r.col == K_S ? C_WARM : vc;
        if (!r.ic.empty()) icon(it, 3, y + (dense ? 2 : 4), r.ic.c_str(), 7, &icc);
        bool big = !dense && numeric(r.val) && r.val.size() <= 4;
        Font *vf = dense ? F.small : big ? F.big : F.mid;
        int vw = text_w(vf, r.val);
        txt(it, F, vf, 191, y + (dense ? 2 : big ? 2 : 4), r.val, vc, 2);
        Font *lf = dense ? F.small : F.mid;
        txt(it, F, lf, 14, y + (dense ? 2 : 4), fit_words(lf, r.label, 191 - vw - 6 - 14), C_WARM);
      }
      break;
    }
    case T_MSG: {
      txt(it, F, F.dest, 4, 13, fit_words(F.dest, c.ti, 186), hc);
      std::vector<std::string> lines;
      wrap(F, F.mid, c.sub, 186, lines);
      int pages = std::max<int>(1, (lines.size() + 1) / 2);
      int pg = ((ms - c.since_ms) / 6000) % pages;
      for (int i = 0; i < 2; i++) {
        size_t li = pg * 2 + i;
        if (li < lines.size()) txt(it, F, F.mid, 4, 31 + i * 12, lines[li], C_PAGER);
      }
      if (pages > 1) meta = std::to_string(pg + 1) + "/" + std::to_string(pages);
      break;
    }
    case T_KPI: {
      int n = std::max<int>(1, c.kpi.size());
      int cw = n == 3 ? 64 : n == 2 ? 96 : 192;
      for (int k = 0; k < (int) c.kpi.size(); k++) {
        const KpiCell &q = c.kpi[k];
        int x = k * cw + 3;
        txt(it, F, F.small, x, 13, fit_words(F.small, q.label, cw - 6), C_SEC);
        Color vc = tokc(q.col);
        int vw = text_w(F.clock, q.val);
        txt(it, F, F.clock, x, 23, q.val, vc);
        if (!q.unit.empty()) txt(it, F, n == 3 ? F.small : F.mid, x + vw + 2, n == 3 ? 30 : 29, q.unit, C_SEC);
        if (!q.sub.empty()) txt(it, F, F.tiny, x, 42, fit_words(F.tiny, q.sub, cw - 6), C_SEC);
        // every cell gets the same dim base line (consistent grid); a percentage fills it
        it.filled_rectangle(x, 50, cw - 8, 2, C_W4);
        if (q.pct >= 0) it.filled_rectangle(x, 50, (cw - 8) * q.pct / 100, 2, vc);
      }
      break;
    }
    case T_RING: {
      Color tc = c.s == 'i' ? C_CATCH : hc;
      if (!c.img.empty() && slot_ready(c.img)) draw_slot(it, c.img, 1, 11, 60, 45);
      else icon(it, 22, 25, c.ic.empty() ? "bell" : c.ic.c_str(), 16, &tc);
      txt(it, F, F.dest, 66, 13, fit_words(F.dest, c.ti, 124), tc);
      txt(it, F, F.mid, 66, 31, fit_words(F.mid, c.sub, 124), C_WARM);
      if (c.at) txt(it, F, F.small, 66, 45, hhmm(c.at), C_SEC);
      break;
    }
    case T_IMG:
      if (c.fb) { draw_slot(it, c.img, 0, 0, 192, 64); return; }
      draw_slot(it, c.img, 0, 11, 192, 45);
      if (!c.ti.empty()) txt(it, F, F.small, 4, 13, c.ti, C_WARM);
      break;
    case T_CV:
      canvas(it, F, c);
      break;
    default: break;
  }
  card_footer(it, F, c, meta);
}

// ------------------------------------------------------------------ panel templates (x128-191)
static void panel_header(Display &it, const Fonts &F, const HaCard &c) {
  it.filled_rectangle(130, 1, 2, 7, tokc(c.tag));
  txt(it, F, F.small, 134, 1, fit_words(F.small, c.ti, 57), sev_color(c));
}

static void card_panel(Display &it, const Fonts &F, const HaCard &c, uint32_t ms) {
  std::string a, b;
  Color hc = sev_color(c);
  switch (c.t) {
    case T_HERO:
      panel_header(it, F, c);
      if (!c.ic.empty()) icon(it, 130, 12, c.ic.c_str(), 9, &hc);
      txt(it, F, F.clock, 189, 22, c.val, hc, 2);
      if (!c.u.empty()) txt(it, F, F.small, 189, 40, c.u, C_SEC, 2);
      split2(c.sub, a, b);
      txt(it, F, F.tiny, 130, 52, fit_words(F.tiny, a.empty() ? b : a, 60), C_SEC);
      break;
    case T_PROG:
      panel_header(it, F, c);
      txt(it, F, F.clock, 189, 14, c.val, C_WARM, 2);
      seg_bar(it, 130, 189, 35, 4, c.pct);
      split2(c.sub, a, b);
      txt(it, F, F.tiny, 130, 44, fit_words(F.tiny, a, 60), C_SEC);
      txt(it, F, F.tiny, 130, 54, fit_words(F.tiny, b, 60), C_WARM);
      break;
    case T_LIST:
      for (size_t i = 0; i < c.rows.size(); i++) {
        const ListRow &r = c.rows[i];
        int y = 4 + i * 15;
        Color vc = tokc(r.col);
        Color icc = r.col == K_S ? C_WARM : vc;
        if (!r.ic.empty()) icon(it, 130, y, r.ic.c_str(), 7, &icc);
        int vw = text_w(F.small, r.val);
        txt(it, F, F.small, 190, y, r.val, vc, 2);
        txt(it, F, F.tiny, 139, y + 1, fit_words(F.tiny, r.label, 190 - vw - 3 - 139), C_WARM);
      }
      break;
    case T_MSG: {
      panel_header(it, F, c);
      std::vector<std::string> lines;
      wrap(F, F.tiny, c.sub, 60, lines);
      int pages = std::max<int>(1, (lines.size() + 5) / 6);
      int pg = ((ms - c.since_ms) / 6000) % pages;
      for (int i = 0; i < 6; i++) {
        size_t li = pg * 6 + i;
        if (li < lines.size()) txt(it, F, F.tiny, 130, 13 + i * 8, lines[li], C_PAGER);
      }
      break;
    }
    case T_KPI:
      for (size_t k = 0; k < c.kpi.size() && k < 2; k++) {
        const KpiCell &q = c.kpi[k];
        int y = 2 + k * 32;
        txt(it, F, F.tiny, 130, y, fit_words(F.tiny, q.label, 60), C_SEC);
        std::string v = q.val + (q.unit.size() <= 1 ? q.unit : "");
        txt(it, F, F.big, 190, y + 9, v, tokc(q.col), 2);
        if (q.unit.size() > 1) txt(it, F, F.tiny, 130, y + 14, q.unit, C_SEC);
        it.filled_rectangle(130, y + 23, 60, 2, C_W4);
        if (q.pct >= 0) it.filled_rectangle(130, y + 23, 60 * q.pct / 100, 2, tokc(q.col));
      }
      break;
    case T_RING: {
      Color tc = c.s == 'i' ? C_CATCH : hc;
      if (!c.img.empty() && slot_ready(c.img)) draw_slot(it, c.img, 128, 0, 64, 44);
      else icon(it, 152, 10, c.ic.empty() ? "bell" : c.ic.c_str(), 16, &tc);
      txt(it, F, F.small, 160, 46, fit_words(F.small, c.ti, 60), tc, 1);
      if (c.at) txt(it, F, F.tiny, 160, 56, hhmm(c.at), C_SEC, 1);
      break;
    }
    case T_IMG:
      if (c.ft.empty()) draw_slot(it, c.img, 128, 0, 64, 64);
      else {
        draw_slot(it, c.img, 128, 0, 64, 55);
        txt(it, F, F.tiny, 130, 57, fit_words(F.tiny, c.ft, 60), C_SEC);
      }
      break;
    case T_CV:
      canvas(it, F, c);
      break;
    default: break;
  }
}

// Departures while a panel card is shown: status shrinks to clock + date, 4 rows on x0-126.
static void panel_departures(Display &it, const Fonts &F, const Frame &fr, const Look &L, const esphome::ESPTime &t) {
  const Strings &s = S(L.ui_lang);
  if (t.is_valid()) {
    char buf[24];
    snprintf(buf, sizeof(buf), "%02d:%02d", t.hour, t.minute);
    txt(it, F, F.mid, 1, 2, buf, C_WARM);
    snprintf(buf, sizeof(buf), "%s %d.%d.", s.wd[t.day_of_week - 1], t.day_of_month, t.month);
    txt(it, F, F.small, 36, 3, buf, C_SEC);
  }
  size_t n = std::min<size_t>(fr.rows.size(), 4);
  for (size_t i = 0; i < n; i++) {
    const Row &r = fr.rows[i];
    int y = 12 + i * 13;
    badge(it, F, 1, y, r.line, 22, 11);
    int mr;
    if (r.mins.empty()) {
      std::string tt = empty_text(r);
      txt(it, F, F.mid, 126, y + 2, tt, C_SEC, 2);
      mr = 126 - text_w(F.mid, tt);
    } else {
      int m0 = r.mins[0];
      Color c = minute_color(m0, r, L);
      if (r.canceled) { txt(it, F, F.mid, 119, y + 2, "X", C_LEAVE, 2); mr = 111; }
      else if (m0 <= 0) { arrows_now(it, 121, y, c); mr = 104; }
      else {
        std::string ms = std::to_string(m0);
        txt(it, F, F.big, 119, y, ms, c, 2);
        txt(it, F, F.small, 120, y, "'", c);
        mr = 119 - text_w(F.big, ms);
      }
      if (r.train && r.delay_min > 0) mr -= delay_chip(it, F, mr - 2, y + 3, r.delay_min) + 2;
    }
    int dw = mr - 27 - 4;
    Color dc = r.canceled ? C_SEC : C_WARM;
    if (!fit_words(F.mid, r.dest, dw).empty()) dest_txt(it, F, F.mid, 27, y + 2, r, dw, dc);
    else dest_txt(it, F, F.tiny, 27, y + 3, r, dw, dc);
  }
}

// ------------------------------------------------------------------ scheduling
// p1 events: full screen for `hold` s after a content change, then panel (z a) for the rest of ttl.
// z f cards (p2/p3): rotation slot of 8 s every 45 s, round robin, >= 30 s after another full card.
// Departures first: while a shown row says "leave now" (red), no card takes the full screen.
// Panel: p2 / z p / p1 after hold; several alternate every 10 s.
struct CardView { const HaCard *full = nullptr, *panel = nullptr; };

static CardView pick_cards(const Frame &fr, uint32_t ms, bool night) {
  CardView v;
  auto &cards = ha_cards();
  if (cards.empty()) return v;
  bool leave_now = false;
  for (size_t i = 0; i < fr.rows.size() && i < 4; i++) {
    const Row &r = fr.rows[i];
    if (!r.stale && !r.mins.empty() && r.mins[0] <= r.walk) leave_now = true;
  }
  static uint32_t last_full_end = 0;
  static const HaCard *last_full = nullptr;
  // 1) p1 events in their hold window (newest first)
  const HaCard *ev = nullptr;
  for (auto &c : cards) {
    char z = card_zone(c);
    if (c.p == 1 && (z == 'e' || z == 'f') && ms - c.since_ms < c.hold * 1000u)
      if (!ev || c.since_ms > ev->since_ms) ev = &c;
  }
  if (ev && night && ev->t != T_RING) ev = nullptr;  // night: only the doorbell goes full screen
  if (ev && !leave_now) v.full = ev;
  // 2) rotation slot for z f cards
  if (!v.full && !leave_now && !night) {
    std::vector<const HaCard *> rot;
    for (auto &c : cards)
      if (card_zone(c) == 'f' && !(c.p == 1 && ms - c.since_ms < c.hold * 1000u)) rot.push_back(&c);
    if (!rot.empty() && (ms / 1000) % 45 < 8 && ms - last_full_end > 30000) {
      v.full = rot[(ms / 45000) % rot.size()];
    }
  }
  if (v.full) last_full = v.full;
  else if (last_full) { last_full = nullptr; last_full_end = ms; }
  if (night) return v;
  // 3) panel
  std::vector<const HaCard *> pan;
  for (auto &c : cards) {
    char z = card_zone(c);
    if (&c == v.full) continue;
    if (z == 'p' || (z == 'e' && c.p == 1) || (leave_now && (z == 'e' || z == 'f') && c.t != T_IMG)) pan.push_back(&c);
  }
  if (!pan.empty()) v.panel = pan[(ms / 10000) % pan.size()];
  return v;
}

}  // namespace perron
