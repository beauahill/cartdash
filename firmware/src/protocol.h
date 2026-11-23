// The USB link messages (docs/usb_protocol.md): building state, hello, and
// log lines, splitting received bytes into lines, and handling cmd lines.
// No Arduino headers, so the native tests check it against protocol/fixtures.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "config.h"
#include "state.h"

// Settings the app can change with set_config. Kept in NVS on the ESP32.
struct Config {
  float wheel_dia_in = DEFAULT_WHEEL_DIA_IN;
  float gear_ratio = DEFAULT_GEAR_RATIO;
  float pulses_per_rev = DEFAULT_PULSES_PER_REV;
  bool speed_src_rpm = DEFAULT_SPEED_SRC_RPM;
  bool sim = DEFAULT_SIM;
};

// Buffer big enough for any line we send, plus the newline and a zero.
constexpr size_t LINE_BUF = MAX_LINE_BYTES + 2;

// Each build_* writes one JSON object followed by '\n' into out and returns
// its length (newline included), or 0 if it did not fit.
size_t build_state(const Snapshot& s, uint32_t seq, uint32_t now_ms, char* out, size_t cap);
size_t build_hello(uint32_t uptime_s, bool sim, char* out, size_t cap);
size_t build_log(const char* lvl, const char* tag, const char* msg, char* out, size_t cap);

// Splits a byte stream into lines. A trailing '\r' is removed, then a line
// longer than MAX_LINE_BYTES is dropped up to the next newline, the same as
// tools/cartdash_proto.py.
class LineReader {
 public:
  // Feed one byte. Returns true when a complete line is ready in line().
  bool feed(char c);
  const char* line() const { return buf_; }
  size_t length() const { return len_; }

 private:
  char buf_[MAX_LINE_BYTES + 2] = {};  // room for a '\r' and the zero
  size_t len_ = 0;
  bool overflow_ = false;
  bool ready_ = false;
};

// Result of handling one received line.
struct CmdResult {
  bool is_cmd = false;          // false: not a cmd message, nothing to answer
  bool config_changed = false;  // save the config to NVS
  bool can_log_changed = false;
};

// Handles one received line. If it is a cmd, applies it to cfg or can_log and
// writes the reply log line (with newline) into reply. Anything that is not a
// valid JSON object with type "cmd" is ignored, per the protocol rules.
CmdResult handle_line(const char* line, size_t len, Config& cfg, bool& can_log, char* reply, size_t reply_cap);
