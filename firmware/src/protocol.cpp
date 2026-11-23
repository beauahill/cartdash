#include "protocol.h"

#include <ArduinoJson.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

// Round to the number of decimals the wire uses, so 14.2f goes out as 14.2
// and not 14.19999981.
static double rounded(float v, int8_t decimals) {
  double scale = pow(10.0, decimals);
  return round(static_cast<double>(v) * scale) / scale;
}

static size_t finish(JsonDocument& doc, char* out, size_t cap) {
  if (doc.overflowed()) return 0;
  size_t need = measureJson(doc);
  if (need + 2 > cap || need > MAX_LINE_BYTES) return 0;
  size_t n = serializeJson(doc, out, cap);
  out[n++] = '\n';
  out[n] = '\0';
  return n;
}

size_t build_state(const Snapshot& s, uint32_t seq, uint32_t now_ms, char* out, size_t cap) {
  JsonDocument doc;
  doc["type"] = "state";
  doc["seq"] = seq;
  doc["t"] = now_ms;
  for (uint8_t i = 0; i < FIELD_COUNT; i++) {
    if (!s.has[i]) continue;  // never read: leave it out
    const FieldInfo& info = FIELD_INFO[i];
    switch (info.kind) {
      case K_NUM:
        if (info.decimals == 0) {
          doc[info.name] = static_cast<long>(lroundf(s.num[i]));
        } else {
          doc[info.name] = rounded(s.num[i], info.decimals);
        }
        break;
      case K_BOOL:
        doc[info.name] = s.flag[i];
        break;
      case K_GEAR: {
        char g[2] = {s.gear, '\0'};
        doc[info.name] = g;  // copied into the document
        break;
      }
      case K_TEXT:
        doc[info.name] = static_cast<const char*>(s.speed_mode);
        break;
      case K_TEMPS: {
        JsonArray a = doc[info.name].to<JsonArray>();
        for (uint8_t k = 0; k < s.temp_count; k++) a.add(static_cast<long>(lroundf(s.temps[k])));
        break;
      }
      case K_FAULTS: {
        const Faults& f = (i == F_KELLY_FAULTS) ? s.kelly_faults : s.bms_faults;
        JsonArray a = doc[info.name].to<JsonArray>();
        for (uint8_t k = 0; k < f.count; k++) a.add(static_cast<const char*>(f.code[k]));
        break;
      }
    }
  }
  JsonArray stale = doc["stale"].to<JsonArray>();
  for (uint8_t i = 0; i < FIELD_COUNT; i++) {
    if (s.is_stale(static_cast<Field>(i), now_ms)) stale.add(FIELD_INFO[i].name);
  }
  return finish(doc, out, cap);
}

size_t build_hello(uint32_t uptime_s, bool sim, char* out, size_t cap) {
  JsonDocument doc;
  doc["type"] = "hello";
  doc["proto"] = PROTO_VERSION;
  doc["fw"] = FW_VERSION;
  doc["uptime_s"] = uptime_s;
  doc["sim"] = sim;
  return finish(doc, out, cap);
}

size_t build_log(const char* lvl, const char* tag, const char* msg, char* out, size_t cap) {
  JsonDocument doc;
  doc["type"] = "log";
  doc["lvl"] = lvl;
  doc["tag"] = tag;
  doc["msg"] = msg;
  return finish(doc, out, cap);
}

bool LineReader::feed(char c) {
  if (ready_) {  // the previous line was handed out, start a new one
    len_ = 0;
    ready_ = false;
  }
  if (c == '\n') {
    bool drop = overflow_;
    overflow_ = false;
    if (drop) {
      len_ = 0;
      return false;
    }
    if (len_ > 0 && buf_[len_ - 1] == '\r') len_--;
    if (len_ > MAX_LINE_BYTES) {
      len_ = 0;
      return false;
    }
    buf_[len_] = '\0';
    ready_ = true;
    return true;
  }
  if (overflow_) return false;
  if (len_ >= MAX_LINE_BYTES + 1) {  // one extra byte for a '\r' before the newline
    overflow_ = true;
    len_ = 0;
    return false;
  }
  buf_[len_++] = c;
  return false;
}

// True for a JSON number that is not a bool. ArduinoJson keeps them apart.
static bool is_number(JsonVariantConst v) { return v.is<double>() && !v.is<bool>(); }

CmdResult handle_line(const char* line, size_t len, Config& cfg, bool& can_log, char* reply, size_t reply_cap) {
  CmdResult r;
  if (len == 0 || len > MAX_LINE_BYTES) return r;
  JsonDocument doc;
  if (deserializeJson(doc, line, len) != DeserializationError::Ok) return r;
  if (!doc.is<JsonObject>()) return r;
  if (!doc["type"].is<const char*>() || strcmp(doc["type"].as<const char*>(), "cmd") != 0) return r;
  // A cmd without its required "cmd" string is dropped unanswered, as in tools/cartdash_proto.py.
  if (!doc["cmd"].is<const char*>()) return r;
  r.is_cmd = true;

  char text[160];
  const char* lvl = "warn";
  JsonVariantConst cmd = doc["cmd"];
  if (strcmp(cmd.as<const char*>(), "set_config") == 0) {
    JsonVariantConst key = doc["key"];
    JsonVariantConst value = doc["value"];
    const char* k = key.is<const char*>() ? key.as<const char*>() : "";
    float* num_target = nullptr;
    if (strcmp(k, "wheel_dia_in") == 0) num_target = &cfg.wheel_dia_in;
    if (strcmp(k, "gear_ratio") == 0) num_target = &cfg.gear_ratio;
    if (strcmp(k, "pulses_per_rev") == 0) num_target = &cfg.pulses_per_rev;

    if (num_target) {
      if (!is_number(value)) {
        snprintf(text, sizeof(text), "set_config rejected: %s needs a number", k);
      } else if (value.as<double>() <= 0.0) {
        snprintf(text, sizeof(text), "set_config rejected: %s must be above zero", k);
      } else {
        *num_target = value.as<float>();
        r.config_changed = true;
        lvl = "info";
        snprintf(text, sizeof(text), "set_config %s=%g ok", k, value.as<double>());
      }
    } else if (strcmp(k, "speed_src") == 0) {
      const char* v = value.is<const char*>() ? value.as<const char*>() : "";
      if (strcmp(v, "rpm") == 0 || strcmp(v, "pulse") == 0) {
        cfg.speed_src_rpm = (strcmp(v, "rpm") == 0);
        r.config_changed = true;
        lvl = "info";
        snprintf(text, sizeof(text), "set_config speed_src=\"%s\" ok", v);
      } else {
        snprintf(text, sizeof(text), "set_config rejected: speed_src must be one of pulse, rpm");
      }
    } else if (strcmp(k, "sim") == 0) {
      if (value.is<bool>()) {
        cfg.sim = value.as<bool>();
        r.config_changed = true;
        lvl = "info";
        snprintf(text, sizeof(text), "set_config sim=%s ok", cfg.sim ? "true" : "false");
      } else {
        snprintf(text, sizeof(text), "set_config rejected: sim needs a bool");
      }
    } else {
      snprintf(text, sizeof(text), "set_config rejected: unknown key '%.40s'", k);
    }
  } else if (strcmp(cmd.as<const char*>(), "can_log") == 0) {
    JsonVariantConst on = doc["on"];
    if (on.is<bool>()) {
      can_log = on.as<bool>();
      r.can_log_changed = true;
      lvl = "info";
      snprintf(text, sizeof(text), "can_log %s ok", can_log ? "on" : "off");
    } else {
      snprintf(text, sizeof(text), "can_log rejected: on must be true or false");
    }
  } else {
    snprintf(text, sizeof(text), "unknown cmd '%.40s'", cmd.as<const char*>());
  }
  build_log(lvl, "cmd", text, reply, reply_cap);
  return r;
}
