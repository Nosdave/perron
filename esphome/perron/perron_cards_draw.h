// Perron – Home Assistant cards v1: drawing + scheduling. Included by perron_render.h right
// before render(); mockups: tools/mockup/scenes_cards.py, spec: docs/cards.md.
//
// Full-screen frame: status bar stays (y0-9), body x1-190 / y11-55, footer y56-63 replaces the
// pager. Panel frame: card on panel 3 (x128-191), departures reflow to x0-126.
#pragma once

#include "perron_cards.h"

namespace perron {

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
    case K_Y: return Color(0xFF, 0xC4, 0x00);
    case K_G: return Color(0x4F, 0xD1, 0x8B);
    case K_B: return Color(0x41, 0xBD, 0xF5);
    case K_V: return Color(0xB4, 0x8C, 0xFF);
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
// card accent: explicit "ac", else the topic (tag) colour
static Color accent(const HaCard &c) { return tokc(c.ac != K_N ? c.ac : c.tag); }
static Color dimc(Color c, int pct = 75) { return Color(c.r * pct / 100, c.g * pct / 100, c.b * pct / 100); }
// cell/row colour: the default warm white means "use the card accent"
static Color cell_accent(const HaCard &c, uint8_t col) { return col == K_W ? accent(c) : tokc(col); }

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
// Fit text into w px: whole words if possible, else cut by characters (never drop everything).
static std::string fit_cut(Font *f, const std::string &s, int w) {
  std::string t = fit_words(f, s, w);
  if (!t.empty() || s.empty() || w <= 0) return t;
  size_t n = utf8_chars(s);
  while (n > 0 && text_w(f, utf8_sub(s, 0, n)) > w) n--;
  return utf8_sub(s, 0, n);
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
static void agenda_rows(Display &it, const Fonts &F, const HaCard &c, uint32_t ms, int x0, int x1, int y0,
                        int pitch, int per_page, Font *f, int time_w);

static void card_full(Display &it, const Fonts &F, const HaCard &c, uint32_t ms) {
  std::string a, b, meta;
  Color hc = sev_color(c);
  if (c.s == 'x') it.horizontal_line(1, 10, 190, C_LEAVE);
  switch (c.t) {
    case T_HERO: {
      int x = 26;
      Color ac = c.s == 'i' ? accent(c) : hc;
      if (!c.ic.empty()) icon(it, 4, 14, c.ic.c_str(), 16, &ac);
      else x = 4;
      int vw = text_w(F.clock, c.val);
      txt(it, F, F.clock, x, 16, c.val, c.s == 'i' ? C_WARM : hc);
      if (!c.u.empty()) txt(it, F, F.mid, x + vw + 3, 22, c.u, dimc(ac));
      txt(it, F, F.dest, x, 37, fit_words(F.dest, c.ti, 118 - x), C_WARM);
      split2(c.sub, a, b);
      txt(it, F, F.small, 190, 18, fit_words(F.small, a, 62), C_WARM, 2);
      txt(it, F, F.small, 190, 30, fit_words(F.small, b, 62), C_SEC, 2);
      break;
    }
    case T_PROG: {
      int x = 26;
      Color ac = c.s == 'i' ? accent(c) : hc;
      if (!c.ic.empty()) icon(it, 4, 13, c.ic.c_str(), 16, &ac);
      else x = 4;
      int vw = text_w(F.big, c.val);
      txt(it, F, F.dest, x, 14, fit_words(F.dest, c.ti, 186 - vw - x - 6), hc);
      txt(it, F, F.big, 190, 13, c.val, C_WARM, 2);
      seg_bar(it, x, 190, 32, 4, c.pct, ac);
      split2(c.sub, a, b);
      txt(it, F, F.small, x, 41, fit_words(F.small, a, 80), dimc(ac, 90));
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
        Color icc = (r.col == K_W || r.col == K_S) ? accent(c) : vc;
        if (!r.ic.empty()) icon(it, 3, y + (dense ? 2 : 4), r.ic.c_str(), 7, &icc);
        bool big = !dense && numeric(r.val) && r.val.size() <= 4;
        Font *vf = dense ? F.small : big ? F.big : F.mid;
        int vw = text_w(vf, r.val);
        txt(it, F, vf, 191, y + (dense ? 2 : big ? 2 : 4), r.val, vc, 2);
        Font *lf = dense ? F.small : F.mid;
        txt(it, F, lf, 14, y + (dense ? 2 : 4), fit_cut(lf, r.label, 191 - vw - 6 - 14), C_WARM);
      }
      break;
    }
    case T_MSG: {
      Color tcol = c.s == 'i' ? accent(c) : hc;
      int tx = 4;
      if (!c.ic.empty()) { icon(it, 4, 12, c.ic.c_str(), 16, &tcol); tx = 24; }
      txt(it, F, F.dest, tx, 13, fit_words(F.dest, c.ti, 164 - tx), tcol);
      std::vector<std::string> lines;
      wrap(F, F.mid, c.sub, 186, lines);
      int pages = std::max<int>(1, (lines.size() + 1) / 2);
      int pg = ((ms - c.since_ms) / 6000) % pages;
      for (int i = 0; i < 2; i++) {
        size_t li = pg * 2 + i;
        if (li < lines.size()) txt(it, F, F.mid, 4, 31 + i * 12, lines[li], C_PAGER);
      }
      if (pages > 1) txt(it, F, F.small, 191, 15, std::to_string(pg + 1) + "/" + std::to_string(pages), C_SEC, 2);
      break;
    }
    case T_KPI: {
      int n = std::max<int>(1, c.kpi.size());
      int cw = n == 3 ? 64 : n == 2 ? 96 : 192;
      for (int k = 0; k < (int) c.kpi.size(); k++) {
        const KpiCell &q = c.kpi[k];
        int x = k * cw + 3;
        Color ca = cell_accent(c, q.col);
        int lx = x;
        if (!q.ic.empty()) { icon(it, x, 13, q.ic.c_str(), 7, &ca); lx = x + 9; }
        txt(it, F, F.small, lx, 13, fit_words(F.small, q.label, cw - 6 - (lx - x)), ca);
        Color vc = (q.col == K_W || q.col >= K_Y) ? C_WARM : tokc(q.col);
        int vw = text_w(F.clock, q.val);
        txt(it, F, F.clock, x, 23, q.val, vc);
        if (!q.unit.empty()) txt(it, F, n == 3 ? F.small : F.mid, x + vw + 2, n == 3 ? 30 : 29, q.unit, dimc(ca, 85));
        if (!q.sub.empty()) txt(it, F, F.tiny, x, 42, fit_words(F.tiny, q.sub, cw - 6), C_SEC);
        // every cell gets the same dim base line (consistent grid); a percentage fills it
        it.filled_rectangle(x, 50, cw - 8, 2, C_W4);
        if (q.pct >= 0) it.filled_rectangle(x, 50, std::max(2, (cw - 8) * q.pct / 100), 2, ca);
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
      draw_slot(it, c.img, 0, 11, 192, 44);  // keep y55+ free for the info line
      if (!c.ti.empty()) txt(it, F, F.small, 4, 13, c.ti, C_WARM);
      break;
    case T_AGENDA: {
      Color tcol = c.s == 'i' ? accent(c) : hc;
      int tx = 4;
      if (!c.ic.empty()) { icon(it, 4, 12, c.ic.c_str(), 7, &tcol); tx = 14; }
      txt(it, F, F.small, tx, 12, fit_words(F.small, c.ti, 150), tcol);
      agenda_rows(it, F, c, ms, 4, 190, 22, 11, 3, F.mid, 32);
      break;
    }
    case T_CV:
      canvas(it, F, c);
      break;
    default: break;
  }
  (void) meta;  // the info line (pager) keeps running below every card (drawn by render())
}

// ------------------------------------------------------------------ panel templates (x128-191)
static void panel_header(Display &it, const Fonts &F, const HaCard &c, bool with_icon = true) {
  Color tc = c.s == 'i' ? accent(c) : sev_color(c);
  int x = 134;
  if (with_icon && !c.ic.empty()) { icon(it, 130, 1, c.ic.c_str(), 7, &tc); x = 139; }
  else it.filled_rectangle(130, 1, 2, 7, tokc(c.tag));
  txt(it, F, F.small, x, 1, fit_words(F.small, c.ti, 191 - x), tc);
}

// Agenda rows: time column + (optional) icon + text; the row colour marks now / next.
static void agenda_rows(Display &it, const Fonts &F, const HaCard &c, uint32_t ms, int x0, int x1, int y0,
                        int pitch, int per_page, Font *f, int time_w) {
  int pages = std::max<int>(1, (c.rows.size() + per_page - 1) / per_page);
  int pg = ((ms - c.since_ms) / 6000) % pages;
  for (int i = 0; i < per_page; i++) {
    size_t k = pg * per_page + i;
    if (k >= c.rows.size()) break;
    const ListRow &r = c.rows[k];
    int y = y0 + i * pitch;
    Color tc = r.col == K_W ? C_WARM : tokc(r.col);
    txt(it, F, f, x0, y, fit_cut(f, r.val, time_w), r.col == K_S ? C_SEC : tc);
    int x = x0 + time_w + 3;
    if (!r.ic.empty() && f != F.tiny) {
      Color icc = r.col == K_W || r.col == K_S ? accent(c) : tc;
      icon(it, x, y + cap_h(f, F) - 7, r.ic.c_str(), 7, &icc);
      x += 9;
    }
    txt(it, F, f, x, y, fit_cut(f, r.label, x1 - x), r.col == K_S ? C_SEC : C_WARM);
  }
  // page counter in the header line (never on top of the info line at the bottom)
  if (pages > 1) txt(it, F, F.tiny, x1, y0 - (f == F.tiny ? 10 : 9), std::to_string(pg + 1) + "/" + std::to_string(pages), C_SEC, 2);
}

static void card_panel(Display &it, const Fonts &F, const HaCard &c, uint32_t ms) {
  std::string a, b;
  Color hc = sev_color(c);
  switch (c.t) {
    case T_HERO: {
      panel_header(it, F, c);
      Color ac = c.s == 'i' ? accent(c) : hc;
      if (!c.ic.empty()) icon(it, 130, 14, c.ic.c_str(), 16, &ac);
      txt(it, F, F.clock, 189, 14, c.val, c.s == 'i' ? C_WARM : hc, 2);
      if (!c.u.empty()) txt(it, F, F.small, 189, 30, c.u, dimc(ac, 85), 2);
      split2(c.sub, a, b);
      txt(it, F, F.tiny, 130, 41, fit_words(F.tiny, a, 60), C_SEC);
      txt(it, F, F.tiny, 130, 48, fit_words(F.tiny, b, 60), C_SEC);
      break;
    }
    case T_PROG:
      panel_header(it, F, c);
      txt(it, F, F.clock, 189, 14, c.val, C_WARM, 2);
      seg_bar(it, 130, 189, 35, 4, c.pct, accent(c));
      split2(c.sub, a, b);
      txt(it, F, F.tiny, 130, 44, fit_words(F.tiny, a, 60), dimc(accent(c), 90));
      txt(it, F, F.tiny, 130, 54, fit_words(F.tiny, b, 60), C_WARM);
      break;
    case T_LIST: {
      bool head = !c.ti.empty();
      if (head) panel_header(it, F, c);
      for (size_t i = 0; i < c.rows.size() && i < (head ? 4u : 4u); i++) {
        const ListRow &r = c.rows[i];
        int y = head ? 13 + i * 12 : 4 + i * 15;
        Color vc = tokc(r.col);
        Color icc = (r.col == K_W || r.col == K_S) ? accent(c) : vc;
        if (!r.ic.empty()) icon(it, 130, y, r.ic.c_str(), 7, &icc);
        int vw = text_w(F.small, r.val);
        txt(it, F, F.small, 190, y, r.val, vc, 2);
        txt(it, F, F.tiny, 139, y + 1, fit_cut(F.tiny, r.label, 190 - vw - 3 - 139), C_WARM);
      }
      break;
    }
    case T_AGENDA:
      panel_header(it, F, c);
      agenda_rows(it, F, c, ms, 130, 190, 12, 8, 5, F.tiny, 24);
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
        Color ca = cell_accent(c, q.col);
        txt(it, F, F.tiny, 130, y, fit_words(F.tiny, q.label, 60), ca);
        std::string v = q.val + (q.unit.size() <= 1 ? q.unit : "");
        txt(it, F, F.big, 190, y + 9, v, C_WARM, 2);
        if (q.unit.size() > 1) txt(it, F, F.tiny, 130, y + 14, q.unit, dimc(ca, 85));
        it.filled_rectangle(130, y + 23, 60, 2, C_W4);
        if (q.pct >= 0) it.filled_rectangle(130, y + 23, std::max(2, 60 * q.pct / 100), 2, ca);
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
    txt(it, F, F.small, 1, 1, buf, C_WARM);
    snprintf(buf, sizeof(buf), "%s %d.%d.", s.wd[t.day_of_week - 1], t.day_of_month, t.month);
    txt(it, F, F.small, 34, 1, buf, C_SEC);
  }
  // 4 rows at 11 px (like the 4-row layout) leave y55-63 for the running info line
  size_t n = std::min<size_t>(fr.rows.size(), 4);
  for (size_t i = 0; i < n; i++) {
    const Row &r = fr.rows[i];
    int y = 10 + i * 11;
    badge(it, F, 1, y, r.line, 22, 10);
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
