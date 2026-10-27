// Perron – video cards: a live stream of small JPEG frames over UDP, prepared by Home Assistant
// (Perron Studio's video filter: any source -> ffmpeg -> the layout's video area).
//
//   HA  --(encrypted API action video_start: session, key, layout, title, seconds)-->  board
//   HA  --(UDP :4049, JPEG frames in chunks, each chunk authenticated)------------->  board
//
// Packet: "PV" | 2 | 0 | session (8) | frame (u16 LE) | chunk | chunks | JPEG bytes (<= 1400)
//         | HMAC-SHA256(key, everything before)[:8]
// Only packets of the announced session with a valid MAC count, so nobody else in the LAN can
// put pictures on the board or disturb a stream. A frame is shown when all of its chunks arrived;
// a newer frame drops an incomplete older one.
// Receiving and decoding run in their own task (core 0) once the network is up; the display
// lambda only copies the finished frame (double buffer). Without frames for 5 s, or after the
// time asked for, the card ends by itself. Alarms (p0) and a ringing doorbell take precedence; the
// stream keeps running underneath and shows again afterwards.
#pragma once

#include <JPEGDEC.h>

#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <new>
#include <string>

#include "esp_heap_caps.h"
#include "esphome/components/network/util.h"
#include "esphome/core/log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include "mbedtls/md.h"

namespace perron {

static const uint16_t VIDEO_PORT = 4049;
static const size_t VIDEO_MAX_CHUNKS = 32;
static const size_t VIDEO_CHUNK = 1400;
static const size_t VIDEO_HDR = 16;
static const size_t VIDEO_MAC = 8;

struct VideoArea { int x, y, w, h; };
// f full bleed | b between status bar and info line | s left half + text | p right panel tile
static VideoArea video_area(char layout) {
  switch (layout) {
    case 'b': return {0, 11, 192, 44};
    case 's': return {0, 0, 96, 64};
    case 'p': return {129, 10, 62, 44};
    default: return {0, 0, 192, 64};
  }
}

struct VideoState {
  // Written by video_start/stop (main loop) under mtx; the receive task copies what it needs
  // under mtx per packet. gen changes with every start/stop: work of an older stream is dropped.
  volatile uint32_t gen = 0;
  volatile bool active = false;
  uint8_t session[8] = {0};
  uint8_t key[16] = {0};
  char layout = 'f';
  std::string title, sub;              // main loop only
  uint32_t start_ms = 0, until_ms = 0; // main loop only
  // receive task only
  uint32_t rx_gen = 0;
  uint8_t *rx = nullptr;               // reassembly buffer (PSRAM)
  uint32_t rx_len[VIDEO_MAX_CHUNKS] = {0};
  uint32_t got = 0;                    // bit mask of received chunks
  int cur_frame = -1, cur_chunks = 0, done_frame = -1;
  mbedtls_md_context_t md;
  int dec_w = 0, dec_h = 0;            // area being decoded into
  uint32_t k_smooth = 256;             // brightness factor, smoothed over frames
  JPEGDEC *jpeg = nullptr;
  // shared (under mtx)
  uint16_t *buf[2] = {nullptr, nullptr};  // RGB565, video area size
  int buf_w[2] = {0, 0}, buf_h[2] = {0, 0};
  int front = 0;
  bool has_frame = false;
  volatile uint32_t last_frame_ms = 0;
  volatile uint32_t frames = 0, dropped = 0, bad = 0;
  SemaphoreHandle_t mtx = nullptr;
};
inline VideoState &video() { static VideoState v; return v; }
inline float &video_fps() { static float f = 0; return f; }
// mean-luminance cap for video frames in % (setting "Video-Bildhelligkeit"); pictures keep 35 %
inline float &video_luma_cap() { static float c = 55; return c; }

static int video_draw_cb(JPEGDRAW *d) {
  VideoState &v = video();
  uint16_t *dst = v.buf[1 - v.front];  // back buffer: only this task writes it
  for (int y = 0; y < d->iHeight; y++) {
    int ty = d->y + y;
    if (ty < 0 || ty >= v.dec_h) continue;
    const uint16_t *src = d->pPixels + y * d->iWidth;
    for (int x = 0; x < d->iWidthUsed; x++) {
      int tx = d->x + x;
      if (tx >= 0 && tx < v.dec_w) dst[ty * v.dec_w + tx] = src[x];
    }
  }
  return 1;
}

// Like clamp_luma for pictures, but with its own cap (video_luma_cap, default 55 %): mean luminance
// limited, smoothed over frames so scene changes do not make the brightness jump.
static void video_clamp(VideoState &v, uint16_t *px, size_t n) {
  uint64_t sum = 0;
  for (size_t i = 0; i < n; i++) {
    uint16_t c = px[i];
    sum += ((c >> 11) * 2 * 77 + ((c >> 5) & 0x3F) * 150 + (c & 0x1F) * 2 * 29);
  }
  uint32_t mean = sum / n;                 // 0 .. 63*256
  const uint32_t cap = (uint32_t) (63 * 256 * std::max(10.0f, std::min(100.0f, video_luma_cap())) / 100);
  uint32_t k = mean > cap ? cap * 256 / mean : 256;
  v.k_smooth = (v.k_smooth * 3 + k) / 4;
  uint32_t kk = std::min<uint32_t>(v.k_smooth, 256);
  if (kk >= 256) return;
  for (size_t i = 0; i < n; i++) {
    uint16_t c = px[i];
    uint32_t r = ((c >> 11) * kk) >> 8, g = (((c >> 5) & 0x3F) * kk) >> 8, b = ((c & 0x1F) * kk) >> 8;
    px[i] = (r << 11) | (g << 5) | b;
  }
}

static void video_decode(VideoState &v, uint32_t gen, char layout, const uint8_t *data, size_t len) {
  VideoArea a = video_area(layout);
  v.dec_w = a.w;
  v.dec_h = a.h;
  int back = 1 - v.front;
  memset(v.buf[back], 0, size_t(a.w) * a.h * 2);
  if (!v.jpeg->openRAM(const_cast<uint8_t *>(data), len, video_draw_cb)) { v.bad++; return; }
  // HA sends exactly the area size; anything else (or progressive) is refused before decoding
  if (v.jpeg->getJPEGType() != JPEG_MODE_BASELINE || v.jpeg->getWidth() > a.w || v.jpeg->getHeight() > a.h) {
    v.jpeg->close();
    v.bad++;
    return;
  }
  v.jpeg->setPixelType(RGB565_LITTLE_ENDIAN);
  bool ok = v.jpeg->decode(0, 0, 0);
  v.jpeg->close();
  if (!ok) { v.bad++; return; }
  video_clamp(v, v.buf[back], size_t(a.w) * a.h);
  uint32_t now = esphome::millis();
  xSemaphoreTake(v.mtx, portMAX_DELAY);
  if (gen == v.gen && v.active) {  // still the same stream
    v.buf_w[back] = a.w;
    v.buf_h[back] = a.h;
    v.front = back;
    v.has_frame = true;
    v.last_frame_ms = now;
    v.frames++;
  }
  xSemaphoreGive(v.mtx);
}

static bool video_mac_ok(VideoState &v, const uint8_t *p, size_t n) {
  uint8_t mac[32];
  mbedtls_md_hmac_reset(&v.md);
  mbedtls_md_hmac_update(&v.md, p, n - VIDEO_MAC);
  mbedtls_md_hmac_finish(&v.md, mac);
  uint8_t diff = 0;
  for (size_t i = 0; i < VIDEO_MAC; i++) diff |= mac[i] ^ p[n - VIDEO_MAC + i];
  return diff == 0;
}

static void video_packet(VideoState &v, const uint8_t *p, int n) {
  if (n < (int) (VIDEO_HDR + VIDEO_MAC) || p[0] != 'P' || p[1] != 'V' || p[2] != 2) return;
  // snapshot of the stream this packet must belong to
  xSemaphoreTake(v.mtx, portMAX_DELAY);
  bool active = v.active;
  uint32_t gen = v.gen;
  char layout = v.layout;
  bool same = active && memcmp(p + 4, v.session, 8) == 0;
  bool new_key = same && gen != v.rx_gen;
  uint8_t key[16];
  if (new_key) memcpy(key, v.key, 16);
  xSemaphoreGive(v.mtx);
  if (!same) return;
  if (new_key) {  // a new stream: fresh reassembly state and HMAC key
    mbedtls_md_hmac_starts(&v.md, key, sizeof(key));
    v.rx_gen = gen;
    v.cur_frame = v.done_frame = -1;
    v.got = 0;
    v.k_smooth = 256;
  }
  if (!video_mac_ok(v, p, n)) { v.bad++; return; }
  int frame = p[12] | (p[13] << 8);
  int chunk = p[14], chunks = p[15];
  size_t len = n - VIDEO_HDR - VIDEO_MAC;
  if (chunks < 1 || chunks > (int) VIDEO_MAX_CHUNKS || chunk >= chunks || len > VIDEO_CHUNK) { v.bad++; return; }
  if (frame == v.done_frame) return;  // a repeat of what is already shown
  if (frame != v.cur_frame) {
    if (v.cur_frame >= 0) {
      int16_t d = (int16_t) (frame - v.cur_frame);
      if (d < 0 && d > -64) return;  // a late packet of an older frame; far back = sender restarted
    }
    if (v.cur_frame >= 0 && v.got) v.dropped++;  // previous never completed
    v.cur_frame = frame;
    v.cur_chunks = chunks;
    v.got = 0;
  }
  if (chunks != v.cur_chunks) { v.bad++; return; }
  memcpy(v.rx + chunk * VIDEO_CHUNK, p + VIDEO_HDR, len);
  v.rx_len[chunk] = len;
  v.got |= 1u << chunk;
  uint32_t all = chunks == 32 ? 0xFFFFFFFFu : ((1u << chunks) - 1);
  if (v.got != all) return;
  size_t total = 0;  // chunks are at fixed offsets; only the last may be short -> compact
  for (int i = 0; i < chunks; i++) {
    if (total != i * VIDEO_CHUNK) memmove(v.rx + total, v.rx + i * VIDEO_CHUNK, v.rx_len[i]);
    total += v.rx_len[i];
  }
  v.got = 0;
  v.done_frame = frame;
  v.cur_frame = -1;
  video_decode(v, gen, layout, v.rx, total);
}

static void video_task(void *) {
  VideoState &v = video();
  static uint8_t pkt[VIDEO_HDR + VIDEO_CHUNK + VIDEO_MAC + 16];
  for (;;) {
    // lwIP exists only once the network component has started: wait for a connection
    while (!esphome::network::is_connected()) vTaskDelay(pdMS_TO_TICKS(500));
    int sock = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(VIDEO_PORT);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    if (sock < 0 || ::bind(sock, (sockaddr *) &addr, sizeof(addr)) != 0) {
      ESP_LOGW("perron.video", "UDP port %u not available yet, retrying", VIDEO_PORT);
      if (sock >= 0) ::close(sock);
      vTaskDelay(pdMS_TO_TICKS(5000));
      continue;
    }
    timeval tv{0, 500000};
    ::setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    ESP_LOGI("perron.video", "listening on UDP %u", VIDEO_PORT);
    for (;;) {
      int n = ::recv(sock, pkt, sizeof(pkt), 0);
      if (n > 0) video_packet(v, pkt, n);
      else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) break;  // socket broke: reopen
    }
    ::close(sock);
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}

// once at boot (on_boot): buffers in PSRAM, decoder, HMAC context, receive task (which itself waits
// for the network before it opens its socket)
inline void video_setup() {
  VideoState &v = video();
  if (v.mtx) return;
  v.mtx = xSemaphoreCreateMutex();
  v.rx = (uint8_t *) heap_caps_malloc(VIDEO_MAX_CHUNKS * VIDEO_CHUNK, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  for (auto &b : v.buf) b = (uint16_t *) heap_caps_calloc(192 * 64, 2, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  void *jm = heap_caps_malloc(sizeof(JPEGDEC), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  mbedtls_md_init(&v.md);
  if (!v.mtx || !v.rx || !v.buf[0] || !v.buf[1] || !jm ||
      mbedtls_md_setup(&v.md, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1) != 0) {
    ESP_LOGE("perron.video", "no memory for video");
    return;  // v.jpeg stays null: video_start refuses
  }
  v.jpeg = new (jm) JPEGDEC();
  xTaskCreatePinnedToCore(video_task, "perron_video", 6144, nullptr, 3, nullptr, 0);
}

static bool video_hex(const std::string &hex, uint8_t *out, size_t n) {
  if (hex.size() != n * 2) return false;
  for (size_t i = 0; i < n; i++) {
    unsigned b;
    if (sscanf(hex.c_str() + i * 2, "%2x", &b) != 1) return false;
    out[i] = (uint8_t) b;
  }
  return true;
}

inline std::string &video_status() { static std::string s = "aus"; return s; }

// API action video_start: HA announces a stream. layout f|b|s|p, seconds 1..900.
inline void video_start(const std::string &session, const std::string &key, const std::string &layout,
                        const std::string &title, const std::string &sub, int seconds) {
  VideoState &v = video();
  if (!v.jpeg) { video_status() = "Fehler: kein Speicher für Video"; ESP_LOGE("perron.video", "no memory"); return; }
  uint8_t s[8], k[16];
  if (!video_hex(session, s, 8) || !video_hex(key, k, 16)) {
    video_status() = "Fehler: Session/Schlüssel ungültig";
    ESP_LOGE("perron.video", "bad session/key");
    return;
  }
  xSemaphoreTake(v.mtx, portMAX_DELAY);
  v.gen++;
  memcpy(v.session, s, 8);
  memcpy(v.key, k, 16);
  v.layout = (layout == "b" || layout == "s" || layout == "p") ? layout[0] : 'f';
  v.has_frame = false;
  v.last_frame_ms = 0;
  v.frames = v.dropped = v.bad = 0;
  v.active = true;
  xSemaphoreGive(v.mtx);
  v.title = led_safe(title.substr(0, 40));
  v.sub = led_safe(sub.substr(0, 120));
  v.start_ms = esphome::millis();
  v.until_ms = v.start_ms + (uint32_t) std::max(1, std::min(900, seconds)) * 1000u;
  video_fps() = 0;
  video_status() = "startet";
}

// API action video_stop: only the stream it names (an empty session stops whatever runs)
inline void video_stop(const std::string &session = "") {
  VideoState &v = video();
  if (!v.mtx) return;
  uint8_t s[8];
  bool named = !session.empty() && video_hex(session, s, 8);
  xSemaphoreTake(v.mtx, portMAX_DELAY);
  if (!named || memcmp(s, v.session, 8) == 0) {
    v.active = false;
    v.has_frame = false;
    v.gen++;
  }
  bool still = v.active;
  xSemaphoreGive(v.mtx);
  if (!still) video_status() = "aus";
}

// main loop, once per frame: ends the card after its time or when frames stop
inline bool video_running() {
  VideoState &v = video();
  if (!v.active) return false;
  uint32_t ms = esphome::millis();
  uint32_t last = v.last_frame_ms;
  bool expired = (int32_t) (ms - v.until_ms) > 0;
  bool stalled = last ? (int32_t) (ms - last) > 5000 : (int32_t) (ms - v.start_ms) > 15000;
  if (expired || stalled) {
    video_stop();
    return false;
  }
  static uint32_t win_ms = 0, win_frames = 0;  // frames per second over 2 s windows
  if (ms - win_ms >= 2000) {
    uint32_t f = v.frames;
    video_fps() = win_ms && f >= win_frames ? (f - win_frames) * 1000.0f / (ms - win_ms) : 0;
    win_ms = ms;
    win_frames = f;
  }
  char b[64];
  snprintf(b, sizeof(b), "läuft %.0f fps, %u verloren, %u fehlerhaft", video_fps(), (unsigned) v.dropped,
           (unsigned) v.bad);
  video_status() = b;
  return v.has_frame;
}

static void video_blit(Display &it, const VideoArea &a) {
  VideoState &v = video();
  if (xSemaphoreTake(v.mtx, 0) != pdTRUE) return;  // decoder swapping right now: next frame
  int f = v.front;
  if (v.has_frame && v.buf_w[f] == a.w && v.buf_h[f] == a.h)
    it.draw_pixels_at(a.x, a.y, a.w, a.h, (const uint8_t *) v.buf[f], esphome::display::COLOR_ORDER_RGB,
                      esphome::display::COLOR_BITNESS_565, false);
  xSemaphoreGive(v.mtx);
}

// Draws the video card. Returns false if no video is to be shown (the board draws as usual).
static bool video_card(Display &it, const Fonts &F, const Frame &fr, const Look &L, const esphome::ESPTime &t,
                       uint32_t now) {
  if (!video_running()) return false;
  VideoState &v = video();
  VideoArea a = video_area(v.layout);
  static const Color C_VID(0x41, 0xBD, 0xF5);
  switch (v.layout) {
    case 'b':
      status_bar(it, F, fr.m, L, t, false, now);
      video_blit(it, a);
      if (L.pager) pager(it, F, fr.pager, L, 55);
      break;
    case 's': {
      video_blit(it, a);
      it.filled_rectangle(100, 2, 2, 7, C_VID);
      txt(it, F, F.small, 104, 2, fit_words(F.small, v.title, 86), C_VID);
      std::vector<std::string> lines;
      wrap(F, F.mid, v.sub, 88, lines);
      for (size_t i = 0; i < lines.size() && i < 4; i++) txt(it, F, F.mid, 102, 14 + i * 11, lines[i], C_WARM);
      break;
    }
    case 'p':
      panel_departures(it, F, fr, L, t);
      it.filled_rectangle(130, 1, 2, 7, C_VID);
      txt(it, F, F.small, 134, 1, fit_words(F.small, v.title, 56), C_VID);
      video_blit(it, a);
      if (L.pager) pager(it, F, fr.pager, L, 55, 120);
      break;
    default:
      video_blit(it, a);
  }
  return true;
}

}  // namespace perron
