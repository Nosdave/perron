// Perron – HTTP endpoints for "Perron Studio" (Home Assistant companion):
//   GET  /perron/screen.bmp            what the board shows right now (192x64, 24-bit BMP)
//   POST /perron/preview  card=<json>&zone=f|p|l
//                                       renders a card exactly like the board would, without
//                                       showing it (f full screen, p panel 3, l info line)
// Rendering always happens on the main loop (inside the display lambda); the HTTP task only
// posts a request and waits for the finished image.
#pragma once

#include <cstring>
#include <string>
#include <vector>

#include "esphome/components/web_server_base/web_server_base.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

#include "perron_render.h"

namespace perron {

// Display that records pixels (RGB565) and optionally forwards them to the real panel.
class CaptureDisplay : public esphome::display::Display {
 public:
  uint16_t px[192 * 64];
  Display *fwd = nullptr;
  void clear() { memset(px, 0, sizeof(px)); }
  void draw_pixel_at(int x, int y, Color c) override {
    if (x < 0 || y < 0 || x >= 192 || y >= 64) return;
    if (!this->get_clipping().inside(x, y)) return;
    px[y * 192 + x] = (uint16_t) (((c.r & 0xF8) << 8) | ((c.g & 0xFC) << 3) | (c.b >> 3));
    if (fwd) fwd->draw_pixel_at(x, y, c);
  }
  int get_width_internal() override { return 192; }
  int get_height_internal() override { return 64; }
  esphome::display::DisplayType get_display_type() override { return esphome::display::DisplayType::DISPLAY_TYPE_COLOR; }
  void update() override {}
};

inline CaptureDisplay *capture() {
  static CaptureDisplay *c = new CaptureDisplay();  // 24 KB -> PSRAM (SPIRAM_USE_MALLOC)
  return c;
}

struct StudioReq {
  volatile int kind = 0;  // 0 idle, 1 live screen, 2 preview
  volatile bool done = false;
  std::string card, err;
  char zone = 'f';
  bool night = false;  // board is in its night window (panel/info-line cards are not shown then)
  std::vector<uint8_t> bmp;
};
inline StudioReq &studio_req() { static StudioReq r; return r; }
// Access token for the Studio endpoints. Set by the Home Assistant integration over the
// encrypted ESPHome API (action set_studio_token), stored on the board, never shown in the LAN.
inline std::string &studio_token() { static std::string t; return t; }
static bool token_ok(const std::string &given) {
  const std::string &t = studio_token();
  if (t.size() < 16 || given.size() != t.size()) return false;
  uint8_t d = 0;
  for (size_t i = 0; i < t.size(); i++) d |= (uint8_t) (t[i] ^ given[i]);  // constant time
  return d == 0;
}
inline SemaphoreHandle_t &studio_mtx() { static SemaphoreHandle_t m = xSemaphoreCreateMutex(); return m; }

static void make_bmp(const uint16_t *px, std::vector<uint8_t> &out) {
  const int W = 192, H = 64, row = W * 3, size = 54 + row * H;
  out.assign(size, 0);
  uint8_t *b = out.data();
  auto u32 = [&](int o, uint32_t v) { b[o] = v; b[o + 1] = v >> 8; b[o + 2] = v >> 16; b[o + 3] = v >> 24; };
  b[0] = 'B'; b[1] = 'M'; u32(2, size); u32(10, 54); u32(14, 40); u32(18, W); u32(22, H);
  b[26] = 1; b[28] = 24; u32(34, row * H); u32(38, 2835); u32(42, 2835);
  for (int y = 0; y < H; y++) {
    uint8_t *d = b + 54 + (H - 1 - y) * row;  // bottom-up
    for (int x = 0; x < W; x++) {
      uint16_t c = px[y * W + x];
      uint8_t r = (c >> 11) & 0x1F, g = (c >> 5) & 0x3F, bl = c & 0x1F;
      d[x * 3 + 0] = (bl << 3) | (bl >> 2);
      d[x * 3 + 1] = (g << 2) | (g >> 4);
      d[x * 3 + 2] = (r << 3) | (r >> 2);
    }
  }
}

// one static info-line item (no scrolling) for previews
static void preview_line(Display &it, const Fonts &F, uint8_t tag, const std::string &text, int avail) {
  it.filled_rectangle(1, 56, 2, 6, tag_color(tag));
  txt(it, F, F.small, 6, 56, fit_words(F.small, text, avail), Color(0xB0, 0xA9, 0x9E));
}

// Parse a card for preview only: never stored, never an alarm (p0 is drawn as p1).
static bool preview_card(const std::string &json, HaCard &out, std::string &err) {
  JsonDocument doc(PsramAllocator::instance());
  if (deserializeJson(doc, json)) { err = "JSON-Fehler"; return false; }
  if ((doc["p"] | 2) < 1) doc["p"] = 1;
  doc["id"] = "__preview";
  std::string j;
  serializeJson(doc, j);
  std::string keep_status = card_status();
  uint32_t keep_gen = cards_gen();
  std::string st = card_json(j);
  auto &v = ha_cards();
  auto it = std::find_if(v.begin(), v.end(), [](const HaCard &c) { return c.id == "__preview"; });
  if (it == v.end()) { err = st; card_status() = keep_status; cards_gen() = keep_gen; return false; }
  out = *it;
  v.erase(it);
  card_status() = keep_status;
  cards_gen() = keep_gen;
  out.since_ms = esphome::millis();
  return true;
}

// Called from the display lambda instead of render(): serves pending Studio requests.
static void render_with_studio(Display &it, const Fonts &F, const Look &L, const esphome::ESPTime &t) {
  StudioReq &rq = studio_req();
  CaptureDisplay *cap = capture();
  if (rq.kind && !rq.done) rq.night = in_night(L, t);
  if (rq.kind == 1 && !rq.done) {  // live: draw normally, recording every pixel
    cap->clear();
    cap->fwd = &it;
    render(*cap, F, L, t);
    cap->fwd = nullptr;
    make_bmp(cap->px, rq.bmp);
    rq.done = true;
    return;
  }
  render(it, F, L, t);
  if (rq.kind == 2 && !rq.done) {  // preview: off screen
    HaCard c;
    if (!preview_card(rq.card, c, rq.err)) { rq.bmp.clear(); rq.done = true; return; }
    if (!c.img.empty()) {  // picture still downloading: HA asks again
      ImgSlot *is = slot(c.img, false);
      if (is && !is->ready && is->url) { rq.err = "Bild lädt"; rq.bmp.clear(); rq.done = true; return; }
    }
    Frame &fr = frame();
    uint32_t now = now_epoch(), ms = esphome::millis();
    cap->fwd = nullptr;
    cap->clear();
    if (rq.zone == 'p') {
      panel_departures(*cap, F, fr, L, t);
      card_panel(*cap, F, c, ms);
      if (!fr.pager.empty()) preview_line(*cap, F, fr.pager[0].tag, fr.pager[0].text, 120);
    } else if (rq.zone == 'l') {
      int y0 = 0;
      if (L.status_bar) {
        if (L.layout == LAYOUT_FOUR) { status_slim(*cap, F, fr.m, L, t, false, now); y0 = 9; }
        else { status_bar(*cap, F, fr.m, L, t, false, now); y0 = 11; }
      }
      if (L.layout == LAYOUT_PREMIUM) layout_premium(*cap, F, fr, L, y0);
      else if (L.layout == LAYOUT_FOUR) layout_four(*cap, F, fr, L, y0);
      else layout_hero(*cap, F, fr, L, y0);
      cap->filled_rectangle(0, 55, 192, 9, Color::BLACK);
      preview_line(*cap, F, (uint8_t) (c.tag >= K_CAL ? c.tag - K_CAL : TAG_HA), card_line(c), 185);
    } else {
      if (!(c.t == T_IMG && c.fb)) status_bar(*cap, F, fr.m, L, t, false, now);
      card_full(*cap, F, c, ms);
      if (!fr.pager.empty() && !(c.t == T_IMG && c.fb)) preview_line(*cap, F, fr.pager[0].tag, fr.pager[0].text, 185);
    }
    make_bmp(cap->px, rq.bmp);
    rq.done = true;
  }
}

// ESPHome's request.send() only knows 200/404/409/500 -> set the real status line via ESP-IDF
static void send_status(AsyncWebServerRequest *request, const char *status, const char *text) {
  httpd_req_t *r = *request;
  httpd_resp_set_status(r, status);
  httpd_resp_set_type(r, "text/plain; charset=utf-8");
  httpd_resp_sendstr(r, text);
}

class StudioHandler : public AsyncWebHandler {
 public:
  bool canHandle(AsyncWebServerRequest *request) const override {
    char buf[AsyncWebServerRequest::URL_BUF_SIZE];
    auto url = request->url_to(buf);
    return strncmp(url.c_str(), "/perron/", 8) == 0;
  }
  void handleRequest(AsyncWebServerRequest *request) override {
    char buf[AsyncWebServerRequest::URL_BUF_SIZE];
    std::string url(request->url_to(buf).c_str());
    int kind = url == "/perron/screen.bmp" ? 1 : url == "/perron/preview" ? 2 : 0;
    if (!kind) { send_status(request, "404 Not Found", "unknown"); return; }
    auto tok = request->get_header("X-Perron-Token");
    if (!tok.has_value() || !token_ok(tok.value())) { send_status(request, "401 Unauthorized", "token"); return; }
    static uint32_t last_ms = 0;  // at most one request every 250 ms
    if (esphome::millis() - last_ms < 250) { send_status(request, "429 Too Many Requests", "slow down"); return; }
    last_ms = esphome::millis();
    if (xSemaphoreTake(studio_mtx(), pdMS_TO_TICKS(3000)) != pdTRUE) { send_status(request, "503 Service Unavailable", "busy"); return; }
    StudioReq &rq = studio_req();
    rq.done = false;
    rq.err.clear();
    if (kind == 2) {
      rq.card = request->arg("card");
      std::string z = request->arg("zone");
      rq.zone = (z == "p" || z == "l") ? z[0] : 'f';
      if (rq.card.empty() || rq.card.size() > 1000) {
        xSemaphoreGive(studio_mtx());
        send_status(request, rq.card.empty() ? "400 Bad Request" : "413 Payload Too Large", rq.card.empty() ? "card fehlt" : "card zu gross");
        return;
      }
    }
    rq.kind = kind;
    for (int i = 0; i < 150 && !rq.done; i++) vTaskDelay(pdMS_TO_TICKS(10));  // max 1.5 s
    rq.kind = 0;
    if (!rq.done) { xSemaphoreGive(studio_mtx()); send_status(request, "504 Gateway Timeout", "timeout"); return; }
    if (rq.bmp.empty()) {
      std::string e = rq.err.empty() ? std::string("Fehler") : rq.err;
      xSemaphoreGive(studio_mtx());
      send_status(request, "400 Bad Request", e.c_str());
      return;
    }
    auto *res = request->beginResponse(200, "image/bmp", rq.bmp.data(), rq.bmp.size());
    res->addHeader("Cache-Control", "no-store");
    res->addHeader("X-Perron-Night", rq.night ? "1" : "0");
    res->addHeader("Access-Control-Allow-Origin", "*");
    request->send(res);
    xSemaphoreGive(studio_mtx());
  }
};

inline void studio_register() {
  static bool done = false;
  if (done || !esphome::web_server_base::global_web_server_base) return;
  esphome::web_server_base::global_web_server_base->add_handler(new StudioHandler());
  done = true;
}

}  // namespace perron
