// Perron – standalone data layer (fetchers + model).
//
// All network fetches run in ONE background FreeRTOS task, so slow servers never block the
// ESPHome loop (web UI, API, display). The display side reads a snapshot of the model under a
// mutex, but only when the model generation changed. Every source has its own interval, error
// backoff, timestamp and error text, so the renderer can show stale data honestly.
//
// JSON is parsed STREAMING straight from the HTTP connection (ArduinoJson custom reader +
// filters) - no full-body buffers, so large feeds (STIB TravellersInformation, big iRail
// stations) cannot be truncated and peak memory stays small. Parsed documents live in PSRAM.
//
// Sources (all keyless except the optional STIB key):
//   STIB      realtime WaitingTimes + TravellersInformation (Belgian Mobility API)
//   SNCB      iRail liveboard (+ connections for the public-transport commute)
//   KMI       app API getForecasts (configured coordinates, default Brussels)
//   BE-Alert  publicalerts.be CapGateway feed (point-in-polygon against the home position)
//   News      Brussels Times WP JSON (tiny) – optional
// Review history: 2 independent agent reviews (correctness/threads, memory/UX) 18.10.2026.
#pragma once

#include <algorithm>
#include <cmath>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>

#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mbedtls/md5.h"

#include <ArduinoJson.h>

namespace perron {

static const char *const TAG = "perron";
static const char *const USER_AGENT = "perron/0.4 (+https://github.com/Nosdave/perron)";

// ------------------------------------------------------------------ configuration
struct Config {
  std::string lang = "de";          // de | fr | nl | en (STIB has fr/nl only -> falls back)
  std::string stib_key;             // optional bmc-partner-key (keyless: tight shared quota)
  std::string stib_points;          // "pointid[:walk_min],..." e.g. "1234:1,2345:5"
  std::string stib_lines;           // optional line filter "92,60"; empty = all
  std::string train_station;        // iRail id "BE.NMBS.00881xxxx"; empty = off
  std::string train_filter;         // "p2" (platform), S-lines or destination substrings
  std::string commute_from, commute_to;  // iRail station ids for the PT commute; empty = off
  float lat = 50.846f, lon = 4.352f;  // home position (weather + BE-Alert); default Brussels centre
  bool weather_on = true, bealert_on = true, news_on = false, disruptions_on = true;
  std::string news_src = "bt";  // news source codes (see NEWS_SOURCES)
  bool any() const { return !stib_points.empty() || !train_station.empty(); }
};

// ------------------------------------------------------------------ model
enum Kind : uint8_t { TRAM = 0, BUS = 1, METRO = 2, TRAIN = 3 };
enum Src : uint8_t { SRC_STIB = 0, SRC_TRAIN, SRC_WX, SRC_BEA, SRC_DISR, SRC_COMMUTE, SRC_NEWS, SRC_N };
static const char *const SRC_NAME[SRC_N] = {"STIB", "Zug", "Wetter", "BE-Alert", "Stoerungen", "Pendeln", "News"};

struct Departure {
  std::string point;    // STIB pointid (per-stop walking time)
  std::string line;     // "81", "71", "S5", "IC"
  std::string dest;     // display form, e.g. "Montgomery"
  uint32_t when = 0;    // epoch (expected, without train delay)
  int16_t delay_s = 0;  // trains: delay in seconds
  bool canceled = false;
  std::string platform;
};

struct Weather {
  bool valid = false;
  int temp = 0, tmin = 0, tmax = 0;
  bool has_min = false, has_max = false;
  int ww = 15;
  bool night = false;
  int rain_in_h = -1;        // first hour (0..12) with precipChance >= 60, -1 none
  // KMI radar nowcast (10-min steps at the home position, mm per 10 min)
  uint32_t rain_start = 0;   // epoch of the first wet frame from now on (0 = none in window)
  uint32_t rain_end = 0;     // epoch when it is dry again (0 = beyond the window)
  float rain_peak = 0;       // max mm/10min in the wet spell
  bool raining_now = false;
  std::string warning;       // highest CURRENT KMI warning name
  int warning_level = 0;     // 0 none, 1 yellow, 2 orange, 3 red
};

struct Alert {
  std::string text;
  uint8_t level = 1;         // 1 info, 2 warning, 3 danger
  uint8_t source = 0;        // 0 STIB disruption, 1 BE-Alert, 3 HA critical
  uint32_t expires = 0;      // epoch, 0 = none
};

// Info card pushed from Home Assistant (calendar, car commute, free text, ...).
// tag: 0 calendar, 1 commute, 2 weather, 3 disruption, 4 alert, 5 news, 6 HA/free
struct Card {
  std::string key, text;
  uint8_t tag = 6, prio = 2;
  uint32_t expires = 0;      // epoch; 0 = until removed
  uint32_t ttl = 0;          // seconds (applied once time is synced)
};

struct Model {
  uint32_t gen = 0;          // bumped on every write -> renderer re-snapshots only on change
  std::vector<Card> cards;
  std::vector<Departure> deps;
  std::vector<Departure> trains;
  Weather wx;
  std::vector<Alert> alerts;
  std::vector<std::string> news;
  uint32_t commute_dep = 0;  // public-transport commute: next departure epoch (incl. delay)
  int commute_dur_s = 0;     // station-to-station duration
  uint32_t ts[SRC_N] = {0};  // last success per source (epoch)
  std::string err[SRC_N];    // last error per source ("" = ok)
  int http[SRC_N] = {0};     // last HTTP status per source
  uint32_t stack_free = 0;   // fetch task stack high-water mark (bytes)
};

// ------------------------------------------------------------------ globals
inline SemaphoreHandle_t &mtx() { static SemaphoreHandle_t m = xSemaphoreCreateMutex(); return m; }
inline Config &cfg_storage() { static Config c; return c; }
inline bool &cfg_dirty() { static bool d = true; return d; }
inline Model &model_storage() { static Model m; return m; }

struct Lock {
  Lock() { xSemaphoreTake(mtx(), portMAX_DELAY); }
  ~Lock() { xSemaphoreGive(mtx()); }
};

inline void set_config(const Config &c) {
  Lock l;
  Config &cur = cfg_storage();
  bool changed = cur.stib_points != c.stib_points || cur.stib_lines != c.stib_lines ||
                 cur.train_station != c.train_station || cur.lang != c.lang || cur.stib_key != c.stib_key ||
                 cur.train_filter != c.train_filter || cur.commute_from != c.commute_from ||
                 cur.commute_to != c.commute_to || std::fabs(cur.lat - c.lat) > 1e-4 ||
                 std::fabs(cur.lon - c.lon) > 1e-4 || cur.weather_on != c.weather_on ||
                 cur.bealert_on != c.bealert_on || cur.news_on != c.news_on || cur.news_src != c.news_src ||
                 cur.disruptions_on != c.disruptions_on;
  cur = c;
  if (changed) cfg_dirty() = true;
}

// Config + dirty flag read and cleared atomically (no lost updates).
inline Config take_config(bool &dirty) {
  Lock l;
  dirty = cfg_dirty();
  cfg_dirty() = false;
  return cfg_storage();
}

inline uint32_t gen() { Lock l; return model_storage().gen; }
inline Model snapshot() { Lock l; return model_storage(); }

inline uint32_t now_epoch() {
  time_t t = ::time(nullptr);
  return t > 1700000000 ? (uint32_t) t : 0;  // 0 = time not synced yet
}
inline uint32_t mono_s() { return (uint32_t) (esp_timer_get_time() / 1000000ULL); }

inline void ok(Src s, int http = 200) {
  Lock l;
  auto &m = model_storage();
  m.ts[s] = now_epoch();
  m.err[s].clear();
  m.http[s] = http;
  m.gen++;
}
inline bool fail(Src s, const std::string &e, int http = 0) {
  ESP_LOGW(TAG, "%s: %s", SRC_NAME[s], e.c_str());
  Lock l;
  model_storage().err[s] = e;
  model_storage().http[s] = http;
  model_storage().gen++;
  return false;
}

// Strip characters the LED fonts cannot draw (emoji etc.): keep ASCII + Latin-1/Latin Ext-A/B.
inline std::string led_safe(const std::string &in) {
  std::string out;
  out.reserve(in.size());
  for (size_t i = 0; i < in.size();) {
    unsigned char c = in[i];
    size_t n = c < 0x80 ? 1 : (c >> 5) == 6 ? 2 : (c >> 4) == 14 ? 3 : 4;
    if (i + n > in.size()) break;
    uint32_t cp = c;
    if (n == 2) cp = ((c & 0x1F) << 6) | (in[i + 1] & 0x3F);
    else if (n == 3) cp = ((c & 0x0F) << 12) | ((in[i + 1] & 0x3F) << 6) | (in[i + 2] & 0x3F);
    else if (n == 4) cp = 0x10000;
    if (cp == '\r' || cp == '\n' || cp == '\t') out += ' ';
    else if (cp >= 0x20 && cp <= 0x24F) out.append(in, i, n);
    else if (cp == 0x2018 || cp == 0x2019) out += '\'';
    else if (cp == 0x201C || cp == 0x201D) out += '"';
    else if (cp == 0x2013 || cp == 0x2014) out += '-';
    i += n;
  }
  return out;
}

// ------------------------------------------------------------------ PSRAM JSON allocator
struct PsramAllocator : ArduinoJson::Allocator {
  void *allocate(size_t n) override {
    void *p = heap_caps_malloc(n, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    return p ? p : malloc(n);
  }
  void deallocate(void *p) override { free(p); }
  void *reallocate(void *p, size_t n) override {
    void *q = heap_caps_realloc(p, n, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    return q ? q : realloc(p, n);
  }
  static PsramAllocator *instance() { static PsramAllocator a; return &a; }
};

// ------------------------------------------------------------------ HTTP (streaming)
// ArduinoJson custom reader over an open esp_http_client (read()/readBytes()).
struct HttpReader {
  esp_http_client_handle_t h;
  char buf[1024];
  int len = 0, pos = 0;
  size_t total = 0, limit;
  bool eof = false;
  HttpReader(esp_http_client_handle_t hh, size_t lim) : h(hh), limit(lim) {}
  bool fill() {
    if (eof || total >= limit) return false;
    len = esp_http_client_read(h, buf, sizeof(buf));
    pos = 0;
    if (len <= 0) { eof = true; len = 0; return false; }
    total += len;
    return true;
  }
  int read() {
    if (pos >= len && !fill()) return -1;
    return (unsigned char) buf[pos++];
  }
  size_t readBytes(char *out, size_t n) {
    size_t got = 0;
    while (got < n) {
      if (pos >= len && !fill()) break;
      size_t k = std::min(n - got, (size_t) (len - pos));
      memcpy(out + got, buf + pos, k);
      pos += k;
      got += k;
    }
    return got;
  }
};

struct Http {
  esp_http_client_handle_t h = nullptr;
  int status = -1;
  ~Http() {
    if (h) { esp_http_client_close(h); esp_http_client_cleanup(h); }
  }
  // Opens the URL (following up to 3 redirects); returns HTTP status or -1.
  int open(const std::string &url, const char *hdr_name = nullptr, const char *hdr_value = nullptr) {
    esp_http_client_config_t c = {};
    c.url = url.c_str();
    c.user_agent = USER_AGENT;
    c.timeout_ms = 15000;
    c.buffer_size = 2048;
    c.buffer_size_tx = 1536;
    c.crt_bundle_attach = esp_crt_bundle_attach;
    c.disable_auto_redirect = true;  // handled below (auto redirect only works with perform())
    h = esp_http_client_init(&c);
    if (!h) return -1;
    if (hdr_name && hdr_value && *hdr_value) esp_http_client_set_header(h, hdr_name, hdr_value);
    esp_http_client_set_header(h, "Accept", "application/json");
    for (int hop = 0; hop < 4; hop++) {
      if (esp_http_client_open(h, 0) != ESP_OK) return status = -1;
      esp_http_client_fetch_headers(h);
      status = esp_http_client_get_status_code(h);
      if (status != 301 && status != 302 && status != 303 && status != 307 && status != 308) break;
      if (esp_http_client_set_redirection(h) != ESP_OK) break;
      esp_http_client_close(h);
    }
    return status;
  }
};

// GET + streaming JSON parse into doc (optionally filtered). Returns "" on success, else error.
inline std::string get_json(const std::string &url, JsonDocument &doc, int &status,
                            const JsonDocument *filter = nullptr, size_t limit = 512 * 1024,
                            const char *hn = nullptr, const char *hv = nullptr) {
  Http http;
  status = http.open(url, hn, hv);
  if (status != 200) return status < 0 ? "Verbindung fehlgeschlagen" : "HTTP " + std::to_string(status);
  HttpReader rd(http.h, limit);
  DeserializationError e = filter ? deserializeJson(doc, rd, DeserializationOption::Filter(*filter),
                                                    DeserializationOption::NestingLimit(12))
                                  : deserializeJson(doc, rd, DeserializationOption::NestingLimit(12));
  if (e) return std::string("JSON ") + e.c_str() + (rd.total >= limit ? " (zu gross)" : "");
  return "";
}

// ------------------------------------------------------------------ helpers
inline int64_t days_from_civil(int y, unsigned m, unsigned d) {
  y -= m <= 2;
  const int era = (y >= 0 ? y : y - 399) / 400;
  const unsigned yoe = (unsigned) (y - era * 400);
  const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097 + (int64_t) doe - 719468;
}

// ISO 8601: "2026-10-18T18:03:45.812+02:00", "...Z", "...+0200", "...T18:03-05:00".
// Without a zone, local time (TZ Europe/Brussels from the sntp component) is assumed.
inline uint32_t parse_iso(const char *s) {
  if (!s || strlen(s) < 16) return 0;
  int Y, M, D, h, m, sec = 0;
  if (sscanf(s, "%4d-%2d-%2dT%2d:%2d", &Y, &M, &D, &h, &m) != 5) return 0;
  const char *p = s + 16;
  if (*p == ':') { sec = atoi(p + 1); p += 3; }
  while (*p == '.' || (*p >= '0' && *p <= '9')) p++;  // fractional seconds
  int64_t t = days_from_civil(Y, M, D) * 86400 + h * 3600 + m * 60 + sec;
  if (*p == 'Z' || *p == 'z') return (uint32_t) t;
  if ((*p == '+' || *p == '-') && isdigit((unsigned char) p[1]) && isdigit((unsigned char) p[2])) {
    int sign = *p == '-' ? -1 : 1;
    p++;
    int oh = (p[0] - '0') * 10 + (p[1] - '0');
    p += 2;
    if (*p == ':') p++;
    int om = (isdigit((unsigned char) p[0]) && isdigit((unsigned char) p[1])) ? (p[0] - '0') * 10 + (p[1] - '0') : 0;
    t -= sign * (oh * 3600 + om * 60);
    return t > 0 ? (uint32_t) t : 0;
  }
  struct tm lt = {};
  lt.tm_year = Y - 1900; lt.tm_mon = M - 1; lt.tm_mday = D; lt.tm_hour = h; lt.tm_min = m; lt.tm_sec = sec;
  lt.tm_isdst = -1;
  time_t loc = mktime(&lt);
  return loc > 0 ? (uint32_t) loc : 0;
}

// UTF-8 aware "GARE DU MIDI" -> "Gare Du Midi" (Latin-1 range, enough for BE names).
inline std::string title_case(const std::string &in) {
  std::string out;
  out.reserve(in.size());
  bool word_start = true;
  for (size_t i = 0; i < in.size(); i++) {
    unsigned char c = in[i];
    if (c == 0xC3 && i + 1 < in.size()) {
      unsigned char n = in[i + 1];
      if (!word_start && n >= 0x80 && n <= 0x9E && n != 0x97) n += 0x20;  // À..Þ -> à..þ
      out += (char) c;
      out += (char) n;
      i++;
      word_start = false;
      continue;
    }
    if (c >= 'A' && c <= 'Z' && !word_start) c = c - 'A' + 'a';
    out += (char) c;
    word_start = (c == ' ' || c == '-' || c == '/' || c == '(' || c == '\'' || c == '.');
  }
  return out;
}

inline std::vector<std::string> split_csv(const std::string &s) {
  std::vector<std::string> v;
  std::string cur;
  for (char ch : s) {
    if (ch == ',' || ch == ';' || ch == ' ') {
      if (!cur.empty()) v.push_back(cur);
      cur.clear();
    } else {
      cur += ch;
    }
  }
  if (!cur.empty()) v.push_back(cur);
  return v;
}

// "1234:1,2345:5" -> {"1234","2345"} (walking minutes are a display concern)
inline std::vector<std::string> point_ids(const std::string &s) {
  std::vector<std::string> v;
  for (auto &t : split_csv(s)) {
    size_t c = t.find(':');
    v.push_back(c == std::string::npos ? t : t.substr(0, c));
  }
  return v;
}

// STIB real-time pointids are numeric: "1234B:5" (GTFS stop_id) -> "1234:5".
inline std::string normalize_points(const std::string &s) {
  std::string o;
  for (auto &t : split_csv(s)) {
    size_t c = t.find(':');
    std::string id = c == std::string::npos ? t : t.substr(0, c);
    while (!id.empty() && isalpha((unsigned char) id.back())) id.pop_back();
    if (id.empty()) continue;
    if (!o.empty()) o += ",";
    o += id + (c == std::string::npos ? "" : t.substr(c));
  }
  return o;
}

inline bool in_list(const std::vector<std::string> &v, const std::string &x) {
  return v.empty() || std::find(v.begin(), v.end(), x) != v.end();
}

inline std::string url_encode(const std::string &s) {
  static const char *hex = "0123456789ABCDEF";
  std::string o;
  for (unsigned char c : s) {
    if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') o += (char) c;
    else { o += '%'; o += hex[c >> 4]; o += hex[c & 15]; }
  }
  return o;
}

// Value as string/int regardless of whether the API sent "81" or 81.
inline std::string as_str(JsonVariantConst v) {
  if (v.is<const char *>()) return v.as<const char *>();
  if (v.is<long>()) return std::to_string(v.as<long>());
  return "";
}
inline long as_int(JsonVariantConst v, long def = 0) {
  if (v.isNull()) return def;
  if (v.is<const char *>()) { const char *s = v.as<const char *>(); return (s && *s) ? atol(s) : def; }
  return v.as<long>();
}

inline const char *pick_lang(JsonVariantConst obj, const std::string &lang) {
  const char *s = obj[lang.c_str()] | (const char *) nullptr;
  if (!s || !*s) s = obj["fr"] | (const char *) nullptr;
  if (!s || !*s) s = obj["nl"] | (const char *) nullptr;
  if (!s || !*s) s = obj["en"] | "";
  return s;
}

// Some STIB fields are JSON encoded as a string, sometimes as a real array -> handle both.
inline JsonVariantConst nested(JsonVariantConst v, JsonDocument &tmp) {
  if (v.is<const char *>()) {
    if (deserializeJson(tmp, v.as<const char *>())) return JsonVariantConst();
    return tmp.as<JsonVariantConst>();
  }
  return v;
}

inline std::string html_unescape(std::string s) {
  struct E { const char *k; const char *v; };
  static const E ents[] = {{"&#8217;", "'"}, {"&#8216;", "'"}, {"&#8220;", "\""}, {"&#8221;", "\""},
                           {"&#8211;", "-"}, {"&#8212;", "-"}, {"&#038;", "&"},  {"&amp;", "&"},
                           {"&quot;", "\""}, {"&#039;", "'"},  {"&#8230;", "..."}, {"&nbsp;", " "}};
  for (auto &e : ents) {
    size_t p;
    while ((p = s.find(e.k)) != std::string::npos) s.replace(p, strlen(e.k), e.v);
  }
  return s;
}

static const char *const STIB_API = "https://api-management-opendata-production.azure-api.net/api/datasets/stibmivb/rt/";

// ------------------------------------------------------------------ STIB departures
inline bool fetch_stib(const Config &c) {
  auto points = point_ids(c.stib_points);
  if (points.empty()) {
    Lock l; model_storage().deps.clear(); model_storage().gen++;
    return true;
  }
  std::string where = "pointid in (";
  for (size_t i = 0; i < points.size(); i++) where += (i ? ",\"" : "\"") + points[i] + "\"";
  where += ")";
  JsonDocument doc(PsramAllocator::instance());
  int st;
  std::string e = get_json(std::string(STIB_API) + "WaitingTimes?limit=50&where=" + url_encode(where), doc, st,
                           nullptr, 64 * 1024, "bmc-partner-key", c.stib_key.c_str());
  if (!e.empty())
    return fail(SRC_STIB, e + ((st == 403 || st == 429) ? " (Limit: STIB-Schluessel eintragen)" : ""), st);
  auto lines = split_csv(c.stib_lines);
  std::vector<Departure> out;
  for (JsonVariantConst r : doc["results"].as<JsonArrayConst>()) {
    std::string line = as_str(r["lineid"]);
    std::string point = as_str(r["pointid"]);
    if (!in_list(lines, line)) continue;
    JsonDocument tmp(PsramAllocator::instance());
    for (JsonVariantConst p : nested(r["passingtimes"], tmp).as<JsonArrayConst>()) {
      Departure d;
      d.point = point;
      d.line = line;
      d.when = parse_iso(p["expectedArrivalTime"] | (const char *) nullptr);
      d.dest = led_safe(title_case(pick_lang(p["destination"], c.lang)));
      if (d.when) out.push_back(d);
    }
  }
  std::sort(out.begin(), out.end(), [](const Departure &a, const Departure &b) { return a.when < b.when; });
  // the feed sometimes lists the same vehicle twice (same platform, line, destination, time)
  for (size_t i = 0; i < out.size(); i++)
    for (size_t j = i + 1; j < out.size() && out[j].when - out[i].when < 30;)
      if (out[j].point == out[i].point && out[j].line == out[i].line && out[j].dest == out[i].dest) out.erase(out.begin() + j);
      else j++;
  {
    Lock l;
    model_storage().deps = std::move(out);
  }
  ok(SRC_STIB);
  return true;
}

inline void clear_alerts(uint8_t source) {
  Lock l;
  auto &al = model_storage().alerts;
  al.erase(std::remove_if(al.begin(), al.end(), [&](const Alert &a) { return a.source == source; }), al.end());
  model_storage().gen++;
}

inline bool fetch_stib_disruptions(const Config &c) {
  if (!c.disruptions_on || c.stib_points.empty()) { clear_alerts(0); return true; }
  JsonDocument filter;
  JsonObject fr = filter["results"].add<JsonObject>();
  fr["lines"] = true; fr["points"] = true; fr["content"] = true; fr["priority"] = true;
  JsonDocument doc(PsramAllocator::instance());
  int st;
  std::string e = get_json(std::string(STIB_API) + "TravellersInformation?limit=100", doc, st, &filter,
                           1024 * 1024, "bmc-partner-key", c.stib_key.c_str());
  if (!e.empty()) return fail(SRC_DISR, e, st);
  auto lines = split_csv(c.stib_lines);
  auto points = point_ids(c.stib_points);
  std::vector<Alert> out;
  uint32_t now = now_epoch();
  for (JsonVariantConst r : doc["results"].as<JsonArrayConst>()) {
    JsonDocument t1(PsramAllocator::instance()), t2(PsramAllocator::instance()), t3(PsramAllocator::instance());
    bool hit = false;
    std::string hit_line;
    for (JsonVariantConst li : nested(r["lines"], t1).as<JsonArrayConst>()) {
      std::string id = as_str(li["id"]);
      if (!lines.empty() && in_list(lines, id)) { hit = true; hit_line = id; }
    }
    for (JsonVariantConst pi : nested(r["points"], t2).as<JsonArrayConst>())
      if (std::find(points.begin(), points.end(), as_str(pi["id"])) != points.end()) hit = true;
    if (!hit) continue;
    JsonVariantConst txt = nested(r["content"], t3)[0]["text"][0];
    Alert a;
    a.text = led_safe((hit_line.empty() ? std::string("STIB") : std::string("STIB ") + hit_line) + ": " +
                      pick_lang(txt, c.lang));
    a.level = as_int(r["priority"], 5) <= 3 ? 2 : 1;
    a.source = 0;
    a.expires = now ? now + 1800 : 0;  // refreshed every 10 min; dropped if fetches keep failing
    out.push_back(a);
    if (out.size() >= 4) break;
  }
  {
    Lock l;
    auto &al = model_storage().alerts;
    al.erase(std::remove_if(al.begin(), al.end(), [](const Alert &a) { return a.source == 0; }), al.end());
    al.insert(al.end(), out.begin(), out.end());
  }
  ok(SRC_DISR);
  return true;
}

// ------------------------------------------------------------------ SNCB (iRail)
inline bool train_filter_ok(const std::string &filter, const Departure &d) {
  if (filter.empty()) return true;
  for (auto &x : split_csv(filter)) {
    if (x.size() > 1 && (x[0] == 'p' || x[0] == 'P') && isdigit((unsigned char) x[1]) && d.platform == x.substr(1))
      return true;
    if (x == d.line) return true;
    if (!x.empty() && d.dest.find(x) != std::string::npos) return true;
  }
  return false;
}

inline std::string irail_lang(const std::string &l) { return (l == "de" || l == "fr" || l == "nl") ? l : "en"; }

inline bool fetch_trains(const Config &c) {
  if (c.train_station.empty()) {
    Lock l; model_storage().trains.clear(); model_storage().gen++;
    return true;
  }
  JsonDocument filter;
  JsonObject f = filter["departures"]["departure"].add<JsonObject>();
  f["station"] = true; f["time"] = true; f["delay"] = true; f["canceled"] = true; f["platform"] = true;
  f["vehicleinfo"]["type"] = true;
  JsonDocument doc(PsramAllocator::instance());
  int st;
  std::string e = get_json("https://api.irail.be/v1/liveboard/?format=json&arrdep=departure&alerts=false&lang=" +
                           irail_lang(c.lang) + "&id=" + url_encode(c.train_station), doc, st, &filter);
  if (!e.empty()) return fail(SRC_TRAIN, e, st);
  std::vector<Departure> out;
  for (JsonVariantConst d : doc["departures"]["departure"].as<JsonArrayConst>()) {
    Departure x;
    x.line = as_str(d["vehicleinfo"]["type"]);
    if (x.line.empty()) x.line = "IC";
    x.dest = led_safe(as_str(d["station"]));
    x.when = (uint32_t) as_int(d["time"]);
    x.delay_s = (int16_t) as_int(d["delay"]);
    x.canceled = as_int(d["canceled"]) != 0;
    x.platform = as_str(d["platform"]);
    if (x.when && train_filter_ok(c.train_filter, x)) out.push_back(x);
    if (out.size() >= 8) break;
  }
  {
    Lock l;
    model_storage().trains = std::move(out);
  }
  ok(SRC_TRAIN);
  return true;
}

inline bool fetch_commute(const Config &c) {
  if (c.commute_from.empty() || c.commute_to.empty()) {
    Lock l; model_storage().commute_dep = 0; model_storage().gen++;
    return true;
  }
  JsonDocument filter;
  JsonObject f = filter["connection"].add<JsonObject>();
  f["duration"] = true; f["departure"]["time"] = true; f["departure"]["delay"] = true;
  f["departure"]["canceled"] = true; f["arrival"]["delay"] = true;
  JsonDocument doc(PsramAllocator::instance());
  int st;
  std::string e = get_json("https://api.irail.be/v1/connections/?format=json&results=3&alerts=false&from=" +
                           url_encode(c.commute_from) + "&to=" + url_encode(c.commute_to), doc, st, &filter);
  if (!e.empty()) return fail(SRC_COMMUTE, e, st);
  uint32_t best = 0;
  int dur = 0;
  for (JsonVariantConst cn : doc["connection"].as<JsonArrayConst>()) {
    if (as_int(cn["departure"]["canceled"])) continue;
    best = (uint32_t) (as_int(cn["departure"]["time"]) + as_int(cn["departure"]["delay"]));
    dur = (int) (as_int(cn["duration"]) + as_int(cn["arrival"]["delay"]) - as_int(cn["departure"]["delay"]));
    break;
  }
  if (!best) return fail(SRC_COMMUTE, "keine Verbindung", st);
  {
    Lock l;
    model_storage().commute_dep = best;
    model_storage().commute_dur_s = dur;
  }
  ok(SRC_COMMUTE);
  return true;
}

// ------------------------------------------------------------------ KMI / IRM
inline std::string kmi_key(const char *method) {
  time_t t = ::time(nullptr);
  struct tm lt;
  localtime_r(&t, &lt);  // TZ set by ESPHome's sntp component (Europe/Brussels)
  char buf[64];
  snprintf(buf, sizeof(buf), "r9EnW374jkJ9acc;%s;%02d/%02d/%04d", method, lt.tm_mday, lt.tm_mon + 1, lt.tm_year + 1900);
  unsigned char md[16];
  mbedtls_md5((const unsigned char *) buf, strlen(buf), md);
  char hex[33];
  for (int i = 0; i < 16; i++) snprintf(hex + i * 2, 3, "%02x", md[i]);
  return hex;
}

inline bool fetch_weather(const Config &c) {
  if (!c.weather_on) {
    Lock l; model_storage().wx = Weather{}; model_storage().gen++;
    return true;
  }
  char coords[64];
  snprintf(coords, sizeof(coords), "&lat=%.4f&long=%.4f", c.lat, c.lon);
  JsonDocument filter;
  filter["obs"] = true;
  JsonObject fd = filter["for"]["daily"].add<JsonObject>();
  fd["tempMin"] = true; fd["tempMax"] = true;
  filter["for"]["hourly"].add<JsonObject>()["precipChance"] = true;
  JsonObject fa = filter["animation"]["sequence"].add<JsonObject>();
  fa["time"] = true; fa["value"] = true;
  JsonObject fw = filter["for"]["warning"].add<JsonObject>();
  fw["warningLevel"] = true; fw["warningType"]["name"] = true; fw["fromTimestamp"] = true; fw["toTimestamp"] = true;
  JsonDocument doc(PsramAllocator::instance());
  int st;
  std::string e = get_json("https://app.meteo.be/services/appv4/?s=getForecasts&k=" + kmi_key("getForecasts") + coords,
                           doc, st, &filter);
  if (!e.empty()) return fail(SRC_WX, e, st);
  Weather w;
  JsonVariantConst obs = doc["obs"];
  if (obs.isNull()) return fail(SRC_WX, "keine Beobachtung", st);
  w.temp = (int) lround(obs["temp"] | 0.0f);
  w.ww = (int) as_int(obs["ww"], 15);
  w.night = strcmp(obs["dayNight"] | "d", "n") == 0;
  for (JsonVariantConst d : doc["for"]["daily"].as<JsonArrayConst>()) {
    if (!d["tempMin"].isNull() && !w.has_min) { w.tmin = (int) as_int(d["tempMin"]); w.has_min = true; }
    if (!d["tempMax"].isNull() && !w.has_max) { w.tmax = (int) as_int(d["tempMax"]); w.has_max = true; }
    if (w.has_min && w.has_max) break;
  }
  if (w.has_min && w.has_max && w.tmin > w.tmax) std::swap(w.tmin, w.tmax);
  int hr = 0;
  for (JsonVariantConst x : doc["for"]["hourly"].as<JsonArrayConst>()) {
    if (hr > 12) break;
    if (as_int(x["precipChance"]) >= 60) { w.rain_in_h = hr; break; }
    hr++;
  }
  uint32_t now = now_epoch();
  // Radar nowcast: frames every 10 min, value = mm/10min at our position. 0.05 mm/10min
  // (~0.3 mm/h) is the "you notice it" threshold.
  {
    const float WET = 0.05f;
    bool in_spell = false;
    for (JsonVariantConst f : doc["animation"]["sequence"].as<JsonArrayConst>()) {
      uint32_t t = parse_iso(f["time"] | (const char *) nullptr);
      float v = f["value"] | 0.0f;
      if (!t || t + 600 <= now) continue;  // past frames
      if (!in_spell && v >= WET && !w.rain_start) {
        in_spell = true;
        w.rain_start = t;
        w.raining_now = t <= now;
      }
      if (in_spell) {
        if (v >= WET) w.rain_peak = std::max(w.rain_peak, v);
        else { w.rain_end = t; break; }
      }
    }
  }
  std::string lang = (c.lang == "fr" || c.lang == "nl" || c.lang == "de") ? c.lang : "en";
  for (JsonVariantConst x : doc["for"]["warning"].as<JsonArrayConst>()) {
    uint32_t from = parse_iso(x["fromTimestamp"] | (const char *) nullptr);
    uint32_t to = parse_iso(x["toTimestamp"] | (const char *) nullptr);
    if (now && ((from && from > now + 3 * 3600) || (to && to < now))) continue;  // current or within 3 h
    int lvl = (int) as_int(x["warningLevel"]);
    if (lvl > w.warning_level) {
      w.warning_level = lvl;
      w.warning = led_safe(pick_lang(x["warningType"]["name"], lang));
    }
  }
  w.valid = true;
  {
    Lock l;
    model_storage().wx = w;
  }
  ok(SRC_WX);
  return true;
}

// ------------------------------------------------------------------ BE-Alert
inline bool point_in_ring(JsonArrayConst pts, float lat, float lon) {
  bool in = false, first = true;
  float px = 0, py = 0, fx = 0, fy = 0;
  for (JsonVariantConst p : pts) {
    float x = p["x"] | 0.0f, y = p["y"] | 0.0f;  // x = longitude, y = latitude (verified on a live sample)
    if (first) { fx = px = x; fy = py = y; first = false; continue; }
    if (((y > lat) != (py > lat)) && (lon < (px - x) * (lat - y) / (py - y) + x)) in = !in;
    px = x; py = y;
  }
  if (!first && ((fy > lat) != (py > lat)) && (lon < (px - fx) * (lat - fy) / (py - fy) + fx)) in = !in;
  return in;
}

inline bool fetch_bealert(const Config &c) {
  if (!c.bealert_on) { clear_alerts(1); return true; }
  JsonDocument filter;
  JsonObject fi = filter["items"].add<JsonObject>();
  fi["title"] = true; fi["description"] = true; fi["expirationDate"] = true;
  JsonObject pt = fi["area"].add<JsonObject>()["coordinates"].add<JsonObject>()["coordinates"].add<JsonObject>();
  pt["x"] = true; pt["y"] = true;
  JsonDocument doc(PsramAllocator::instance());
  int st;
  std::string e = get_json("https://publicalerts.be/CapGateway/feed?outdated=false", doc, st, &filter);
  if (!e.empty()) return fail(SRC_BEA, e, st);
  std::vector<Alert> out;
  uint32_t now = now_epoch();
  for (JsonVariantConst it : doc["items"].as<JsonArrayConst>()) {
    uint32_t exp = parse_iso(it["expirationDate"] | (const char *) nullptr);
    if (exp && now && exp < now) continue;
    bool hit = false;
    for (JsonVariantConst area : it["area"].as<JsonArrayConst>())
      for (JsonVariantConst ring : area["coordinates"].as<JsonArrayConst>())
        if (point_in_ring(ring["coordinates"].as<JsonArrayConst>(), c.lat, c.lon)) hit = true;
    if (!hit) continue;
    Alert a;
    const char *d = it["description"] | (const char *) nullptr;
    a.text = led_safe((d && *d) ? d : (it["title"] | ""));
    a.level = 3;
    a.source = 1;
    a.expires = exp;
    out.push_back(a);
  }
  {
    Lock l;
    auto &al = model_storage().alerts;
    al.erase(std::remove_if(al.begin(), al.end(), [](const Alert &a) { return a.source == 1; }), al.end());
    al.insert(al.begin(), out.begin(), out.end());
  }
  ok(SRC_BEA);
  return true;
}

// ------------------------------------------------------------------ News
// News sources (setting "Nachrichtenquellen": comma list of codes, max 3). Kinds: 0 WordPress REST
// (title.rendered), 1 RSS/Atom (<item>/<entry> titles), 2 tagesschau api2u (news[].title).
struct NewsSrc { const char *code, *tag; uint8_t kind; const char *url; };
static const NewsSrc NEWS_SOURCES[] = {
    {"bt", "BT", 0, "https://api.brusselstimes.com/wp-json/wp/v2/posts?per_page=4&_fields=title&categories=389"},
    {"btb", "BT", 0, "https://api.brusselstimes.com/wp-json/wp/v2/posts?per_page=4&_fields=title&categories=396"},
    {"bteu", "BT", 0, "https://api.brusselstimes.com/wp-json/wp/v2/posts?per_page=4&_fields=title&categories=403"},
    {"btw", "BT", 0, "https://api.brusselstimes.com/wp-json/wp/v2/posts?per_page=4&_fields=title&categories=407"},
    {"bx1", "BX1", 0, "https://bx1.be/wp-json/wp/v2/posts?per_page=4&_fields=title"},
    {"bul", "Bulletin", 1, "https://www.thebulletin.be/rss.xml"},
    {"vrt", "VRT", 1, "https://www.vrt.be/vrtnws/nl.rss.articles.xml"},
    {"llb", "La Libre", 1, "https://www.lalibre.be/arc/outboundfeeds/rss/?outputType=xml"},
    {"en", "Euronews", 1, "https://www.euronews.com/rss?level=theme&name=news"},
    {"enb", "Euronews", 1, "https://www.euronews.com/rss?level=theme&name=business"},
    {"pol", "Politico", 1, "https://www.politico.eu/feed/"},
    {"bbc", "BBC", 1, "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"ts", "tagesschau", 2, "https://www.tagesschau.de/api2u/news/?ressort=inland"},
    {"tsa", "tagesschau", 2, "https://www.tagesschau.de/api2u/news/?ressort=ausland"},
    {"orf", "ORF", 1, "https://rss.orf.at/news.xml"},
};

inline std::string strip_markup(std::string t) {
  size_t a;
  while ((a = t.find("<![CDATA[")) != std::string::npos) t.erase(a, 9);
  while ((a = t.find("]]>")) != std::string::npos) t.erase(a, 3);
  std::string o;
  bool tag = false;
  for (char ch : t) {
    if (ch == '<') tag = true;
    else if (ch == '>') tag = false;
    else if (!tag) o += (ch == '\n' || ch == '\r' || ch == '\t') ? ' ' : ch;
  }
  while (!o.empty() && o.front() == ' ') o.erase(o.begin());
  while (!o.empty() && o.back() == ' ') o.pop_back();
  return o;
}

// Streams an RSS/Atom feed and collects the first n item titles (stops reading after that).
inline std::string rss_titles(const std::string &url, size_t n, std::vector<std::string> &out, int &status) {
  Http http;
  status = http.open(url);
  if (status != 200) return status < 0 ? "Verbindung fehlgeschlagen" : "HTTP " + std::to_string(status);
  HttpReader rd(http.h, 400 * 1024);
  std::string win;          // rolling window of the last characters
  bool in_item = false;
  int ch;
  while (out.size() < n && (ch = rd.read()) >= 0) {
    win += (char) ch;
    if (win.size() > 12) win.erase(0, win.size() - 12);
    auto ends = [&](const char *s) { size_t k = strlen(s); return win.size() >= k && win.compare(win.size() - k, k, s) == 0; };
    if (ends("<item>") || ends("<item ") || ends("<entry>") || ends("<entry ")) in_item = true;
    else if (ends("</item>") || ends("</entry>")) in_item = false;
    else if (in_item && (ends("<title>") || ends("<title "))) {
      if (win.back() == ' ') while ((ch = rd.read()) >= 0 && ch != '>') {}
      std::string t;
      while ((ch = rd.read()) >= 0 && t.size() < 600) {
        t += (char) ch;
        if (t.size() >= 8 && t.compare(t.size() - 8, 8, "</title>") == 0) { t.resize(t.size() - 8); break; }
      }
      t = led_safe(html_unescape(strip_markup(t)));
      if (!t.empty()) out.push_back(t);
      win.clear();
    }
  }
  return out.empty() ? "keine Titel" : "";
}

inline bool fetch_news(const Config &c) {
  if (!c.news_on) {
    Lock l; model_storage().news.clear(); model_storage().gen++;
    return true;
  }
  auto codes = split_csv(c.news_src.empty() ? std::string("bt") : c.news_src);
  if (codes.size() > 3) codes.resize(3);
  std::vector<std::vector<std::string>> per;
  std::string err;
  int st = 0;
  for (auto &code : codes) {
    const NewsSrc *src = nullptr;
    for (auto &s : NEWS_SOURCES)
      if (code == s.code) src = &s;
    if (!src) continue;
    std::vector<std::string> titles;
    std::string e;
    if (src->kind == 1) {
      e = rss_titles(src->url, 3, titles, st);
    } else {
      JsonDocument filter;
      if (src->kind == 0) filter[0]["title"]["rendered"] = true;
      else filter["news"][0]["title"] = true;
      JsonDocument doc(PsramAllocator::instance());
      e = get_json(src->url, doc, st, &filter, 512 * 1024);
      if (e.empty()) {
        JsonArrayConst arr = src->kind == 0 ? doc.as<JsonArrayConst>() : doc["news"].as<JsonArrayConst>();
        for (JsonVariantConst p : arr) {
          if (titles.size() >= 3) break;
          const char *t = src->kind == 0 ? (p["title"]["rendered"] | "") : (p["title"] | "");
          if (*t) titles.push_back(led_safe(html_unescape(t)));
        }
      }
    }
    if (!e.empty()) { err = std::string(src->code) + ": " + e; continue; }
    for (auto &t : titles) t = std::string(src->tag) + ": " + t;
    per.push_back(std::move(titles));
  }
  if (per.empty()) return fail(SRC_NEWS, err.empty() ? "keine Quelle" : err, st);
  std::vector<std::string> out;  // interleave the sources: A1 B1 C1 A2 B2 ...
  for (size_t i = 0; i < 3; i++)
    for (auto &v : per)
      if (i < v.size()) out.push_back(v[i]);
  {
    Lock l;
    model_storage().news = std::move(out);
  }
  ok(SRC_NEWS);
  return true;
}

// ------------------------------------------------------------------ HA push (ESPHome API action)
// prio 0 = full-screen alert, 1..3 = pager priority. Empty message removes the card/alert.
inline void push_card(const std::string &key, const std::string &text, int tag, int prio, int ttl_s) {
  Lock l;
  auto &m = model_storage();
  m.gen++;
  auto &v = m.cards;
  v.erase(std::remove_if(v.begin(), v.end(), [&](const Card &c) { return c.key == key; }), v.end());
  auto &al = m.alerts;
  uint32_t now = now_epoch();
  if (prio <= 0) {
    al.erase(std::remove_if(al.begin(), al.end(), [](const Alert &x) { return x.source == 3; }), al.end());
    if (text.empty()) return;
    Alert a;
    a.text = led_safe(text);
    a.level = 3;
    a.source = 3;
    a.expires = (ttl_s > 0 && now) ? now + ttl_s : 0;
    al.insert(al.begin(), a);
    return;
  }
  if (text.empty()) return;
  Card c;
  c.key = key;
  c.text = led_safe(text);
  c.tag = (uint8_t) std::max(0, std::min(6, tag));
  c.prio = (uint8_t) std::max(1, std::min(3, prio));
  c.ttl = ttl_s > 0 ? ttl_s : 0;
  c.expires = (c.ttl && now) ? now + c.ttl : 0;
  v.push_back(c);
  if (v.size() > 12) v.erase(v.begin());
}

// Demo for the "Warnung testen" button: goes through the exact BE-Alert display path
// (source 1) and expires after ttl_s. The next BE-Alert fetch may clear it earlier.
inline void test_bealert(int ttl_s) {
  Lock l;
  auto &al = model_storage().alerts;
  Alert a;
  a.text = "TEST - Dies ist ein Test der Warnanzeige. Bei einer echten BE-Alert-Meldung fuer "
           "Ihren Standort erscheint hier deren Text. Keine Gefahr.";
  a.level = 3;
  a.source = 1;
  uint32_t now = now_epoch();
  a.expires = now ? now + ttl_s : 0;
  al.insert(al.begin(), a);
  model_storage().gen++;
}

inline void clear_ha_alert() {
  Lock l;
  auto &al = model_storage().alerts;
  al.erase(std::remove_if(al.begin(), al.end(), [](const Alert &x) { return x.source == 3; }), al.end());
  model_storage().gen++;
}

// Cards pushed before SNTP sync: start their TTL once the clock is valid.
inline void fix_card_ttls() {
  uint32_t now = now_epoch();
  if (!now) return;
  Lock l;
  for (auto &c : model_storage().cards)
    if (c.ttl && !c.expires) { c.expires = now + c.ttl; model_storage().gen++; }
}

// ------------------------------------------------------------------ scheduler task
struct Job {
  Src src;
  bool (*fn)(const Config &);
  uint32_t every_s;
  uint32_t next = 0;  // monotonic seconds
  uint8_t fails = 0;
};

inline void fetch_task(void *) {
  // intervals respect provider limits (STIB keyless quota, KMI >= 10 min, iRail 3/s)
  Job jobs[] = {
      {SRC_STIB, fetch_stib, 30},        {SRC_TRAIN, fetch_trains, 60},    {SRC_WX, fetch_weather, 900},
      {SRC_BEA, fetch_bealert, 300},     {SRC_DISR, fetch_stib_disruptions, 600},
      {SRC_COMMUTE, fetch_commute, 300}, {SRC_NEWS, fetch_news, 1800},
  };
  vTaskDelay(pdMS_TO_TICKS(5000));
  for (;;) {
    bool dirty;
    Config c = take_config(dirty);
    if (dirty)
      for (auto &j : jobs) j.next = 0;
    if (now_epoch() && c.any()) {  // TLS + KMI key need valid time
      fix_card_ttls();
      for (auto &j : jobs) {
        if (mono_s() < j.next) continue;
        bool good = j.fn(c);
        j.fails = good ? 0 : std::min<uint8_t>(j.fails + 1, 5);
        // keyless STIB: be gentle, the quota is shared per public IP
        uint32_t every = (j.src == SRC_STIB && c.stib_key.empty()) ? 60 : j.every_s;
        uint32_t wait = good ? every : std::max<uint32_t>(30, every << (j.fails - 1));
        j.next = mono_s() + std::min<uint32_t>(wait, every * 16);
        vTaskDelay(pdMS_TO_TICKS(250));
      }
      Lock l;
      model_storage().stack_free = uxTaskGetStackHighWaterMark(nullptr);
    }
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}

inline void start() {
  static bool started = false;
  if (started) return;
  started = true;
  xTaskCreatePinnedToCore(fetch_task, "perron_fetch", 12288, nullptr, 1, nullptr, 0);
}

}  // namespace perron
