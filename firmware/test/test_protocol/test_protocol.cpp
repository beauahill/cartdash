// The firmware's JSON output and command handling, checked against the shared
// samples in protocol/fixtures (the same files tools/tests/test_protocol.py
// and the Android unit tests read).
#include <ArduinoJson.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <unity.h>

#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "protocol.h"
#include "state.h"

static std::string read_file(const char* name) {
  std::string path = std::string(FIXTURES_DIR) + "/" + name;
  std::ifstream f(path, std::ios::binary);
  TEST_ASSERT_TRUE_MESSAGE(f.good(), path.c_str());
  std::stringstream ss;
  ss << f.rdbuf();
  return ss.str();
}

// Lines split on '\n' only, like the Python test, so a '\r' stays visible.
static std::vector<std::string> lines(const char* name) {
  std::string all = read_file(name);
  std::vector<std::string> out;
  size_t start = 0;
  for (size_t i = 0; i < all.size(); i++) {
    if (all[i] == '\n') {
      out.push_back(all.substr(start, i - start));
      start = i + 1;
    }
  }
  return out;
}

// Value equality: numbers by value (82 equals 82.0), arrays in order except
// "stale", which is a set. A missing key equals null (the spec treats both as "--").
static bool same(JsonVariantConst a, JsonVariantConst b, const char* key = "");

static bool same_object(JsonObjectConst a, JsonObjectConst b) {
  for (JsonPairConst kv : a) {
    if (!same(kv.value(), b[kv.key()], kv.key().c_str())) return false;
  }
  for (JsonPairConst kv : b) {
    if (a[kv.key()].isNull() && !kv.value().isNull()) return false;
  }
  return true;
}

static bool same(JsonVariantConst a, JsonVariantConst b, const char* key) {
  if (a.isNull() || b.isNull()) return a.isNull() && b.isNull();
  if (a.is<bool>() || b.is<bool>()) return a.is<bool>() && b.is<bool>() && a.as<bool>() == b.as<bool>();
  if (a.is<double>() && b.is<double>()) return fabs(a.as<double>() - b.as<double>()) < 1e-9;
  if (a.is<const char*>() && b.is<const char*>()) return strcmp(a.as<const char*>(), b.as<const char*>()) == 0;
  if (a.is<JsonArrayConst>() && b.is<JsonArrayConst>()) {
    JsonArrayConst x = a.as<JsonArrayConst>(), y = b.as<JsonArrayConst>();
    if (x.size() != y.size()) return false;
    if (strcmp(key, "stale") == 0) {
      for (JsonVariantConst v : x) {
        bool found = false;
        for (JsonVariantConst w : y) found = found || same(v, w);
        if (!found) return false;
      }
      return true;
    }
    for (size_t i = 0; i < x.size(); i++)
      if (!same(x[i], y[i])) return false;
    return true;
  }
  if (a.is<JsonObjectConst>() && b.is<JsonObjectConst>()) return same_object(a, b);
  return false;
}

// Fill a State from a fixture state line: the fields named in "stale" get a
// timestamp 2.5 s old, the rest are fresh. Null fields are left unset.
static uint32_t load_state(const std::string& line, State& st) {
  JsonDocument doc;
  TEST_ASSERT_EQUAL(DeserializationError::Ok, deserializeJson(doc, line).code());
  uint32_t now = doc["t"].as<uint32_t>();
  JsonArrayConst stale = doc["stale"].as<JsonArrayConst>();
  for (JsonPairConst kv : doc.as<JsonObjectConst>()) {
    Field f = field_by_name(kv.key().c_str());
    if (f == FIELD_COUNT || kv.value().isNull()) continue;
    uint32_t ts = now;
    for (JsonVariantConst s : stale)
      if (strcmp(s.as<const char*>(), kv.key().c_str()) == 0) ts = now - 2500;
    JsonVariantConst v = kv.value();
    switch (FIELD_INFO[f].kind) {
      case K_NUM: st.set_num(f, v.as<float>(), ts); break;
      case K_BOOL: st.set_bool(f, v.as<bool>(), ts); break;
      case K_GEAR: st.set_gear(v.as<const char*>()[0], ts); break;
      case K_TEXT: st.set_speed_mode(v.as<const char*>(), ts); break;
      case K_TEMPS: {
        float t[MAX_TEMPS];
        size_t n = 0;
        for (JsonVariantConst x : v.as<JsonArrayConst>()) t[n++] = x.as<float>();
        st.set_bms_temps(t, n, ts);
        break;
      }
      case K_FAULTS: {
        std::vector<const char*> codes;
        for (JsonVariantConst x : v.as<JsonArrayConst>()) codes.push_back(x.as<const char*>());
        st.set_faults(f, codes.data(), codes.size(), ts);
        break;
      }
    }
  }
  return now;
}

static void check_state_round_trip(const char* fixture) {
  std::string line = lines(fixture)[0];
  State st;
  uint32_t now = load_state(line, st);
  JsonDocument want;
  deserializeJson(want, line);
  // The firmware always sends "stale", empty when nothing is stale; a missing
  // "stale" in a fixture means the same thing.
  if (want["stale"].isNull()) want["stale"].to<JsonArray>();
  Snapshot snap;
  st.snapshot(snap);
  char buf[LINE_BUF];
  size_t n = build_state(snap, want["seq"].as<uint32_t>(), now, buf, sizeof(buf));
  TEST_ASSERT_TRUE(n > 0);
  TEST_ASSERT_EQUAL_CHAR('\n', buf[n - 1]);
  JsonDocument got;
  TEST_ASSERT_EQUAL(DeserializationError::Ok, deserializeJson(got, buf, n).code());
  TEST_ASSERT_TRUE_MESSAGE(same(got.as<JsonVariantConst>(), want.as<JsonVariantConst>()), buf);
}

void test_state_full_matches_fixture() { check_state_round_trip("state_full.jsonl"); }
void test_state_minimal_matches_fixture() { check_state_round_trip("state_minimal.jsonl"); }
void test_state_stale_matches_fixture() { check_state_round_trip("state_stale.jsonl"); }

void test_staleness_is_decided_at_send_time() {
  State st;
  st.set_num(F_MOTOR_TEMP_F, 121, 1000);
  Snapshot s;
  st.snapshot(s);
  TEST_ASSERT_FALSE(s.is_stale(F_MOTOR_TEMP_F, 3000));  // exactly 2 s: not yet
  TEST_ASSERT_TRUE(s.is_stale(F_MOTOR_TEMP_F, 3001));
  TEST_ASSERT_FALSE(s.is_stale(F_SOC_PCT, 999999));      // never read: missing, not stale
  // millis() wrap
  st.set_num(F_SOC_PCT, 50, 0xFFFFFF00u);
  st.snapshot(s);
  TEST_ASSERT_FALSE(s.is_stale(F_SOC_PCT, 0x00000100u));
  TEST_ASSERT_TRUE(s.is_stale(F_SOC_PCT, 0x00000900u));
}

void test_power_follows_pack() {
  State st;
  st.set_pack(66.4f, -48.5f, 10);
  Snapshot s;
  st.snapshot(s);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -3.2204f, s.num[F_POWER_KW]);
  TEST_ASSERT_TRUE(s.has[F_POWER_KW]);
}

void test_hello_matches_fixture() {
  char buf[LINE_BUF];
  size_t n = build_hello(120, true, buf, sizeof(buf));
  JsonDocument got, want;
  deserializeJson(got, buf, n);
  deserializeJson(want, lines("hello.jsonl")[0]);
  want["fw"] = FW_VERSION;  // the fixture's version string is only an example
  TEST_ASSERT_TRUE_MESSAGE(same(got.as<JsonVariantConst>(), want.as<JsonVariantConst>()), buf);
}

void test_cmd_fixture_all_accepted() {
  Config cfg;
  bool can_log = false;
  char reply[LINE_BUF];
  for (const std::string& line : lines("cmd.jsonl")) {
    CmdResult r = handle_line(line.c_str(), line.size(), cfg, can_log, reply, sizeof(reply));
    TEST_ASSERT_TRUE_MESSAGE(r.is_cmd, line.c_str());
    JsonDocument doc;
    TEST_ASSERT_EQUAL(DeserializationError::Ok, deserializeJson(doc, reply).code());
    TEST_ASSERT_EQUAL_STRING("log", doc["type"]);
    TEST_ASSERT_EQUAL_STRING("cmd", doc["tag"]);
    TEST_ASSERT_EQUAL_STRING_MESSAGE("info", doc["lvl"], reply);
  }
  TEST_ASSERT_FLOAT_WITHIN(1e-6f, 22.0f, cfg.wheel_dia_in);
  TEST_ASSERT_TRUE(cfg.speed_src_rpm);
  TEST_ASSERT_TRUE(cfg.sim);
  TEST_ASSERT_TRUE(can_log);
}

void test_bad_cmds_answered_with_warn() {
  const char* bad[] = {
      R"({"type":"cmd","cmd":"set_config","key":"wheel_dia_in","value":true})",
      R"({"type":"cmd","cmd":"set_config","key":"wheel_dia_in","value":-1})",
      R"({"type":"cmd","cmd":"set_config","key":"speed_src","value":"gps"})",
      R"({"type":"cmd","cmd":"set_config","key":"sim","value":1})",
      R"({"type":"cmd","cmd":"set_config","key":"nope","value":1})",
      R"({"type":"cmd","cmd":"can_log","on":"yes"})",
      R"({"type":"cmd","cmd":"reboot"})",
  };
  for (const char* line : bad) {
    Config cfg;
    bool can_log = false;
    char reply[LINE_BUF];
    CmdResult r = handle_line(line, strlen(line), cfg, can_log, reply, sizeof(reply));
    TEST_ASSERT_TRUE_MESSAGE(r.is_cmd, line);
    TEST_ASSERT_FALSE_MESSAGE(r.config_changed, line);
    JsonDocument doc;
    deserializeJson(doc, reply);
    TEST_ASSERT_EQUAL_STRING_MESSAGE("warn", doc["lvl"], line);
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, DEFAULT_WHEEL_DIA_IN, cfg.wheel_dia_in);
  }
}

// garbage.jsonl through the line reader and the cmd handler: nothing in it is
// a cmd, so nothing is answered and nothing crashes. The over-long line is
// dropped whole by the reader.
void test_garbage_fixture() {
  std::string all = read_file("garbage.jsonl");
  LineReader reader;
  Config cfg;
  bool can_log = false;
  char reply[LINE_BUF];
  int count = 0;
  bool saw_cr = false;
  for (char c : all) {
    if (!reader.feed(c)) continue;
    count++;
    TEST_ASSERT_TRUE(reader.length() <= MAX_LINE_BYTES);
    saw_cr = saw_cr || (reader.length() > 0 && reader.line()[reader.length() - 1] == '\r');
    CmdResult r = handle_line(reader.line(), reader.length(), cfg, can_log, reply, sizeof(reply));
    TEST_ASSERT_FALSE(r.is_cmd);
  }
  TEST_ASSERT_EQUAL(11, count);  // 12 lines, the over-long one dropped
  TEST_ASSERT_FALSE(saw_cr);
}

static int count_lines(const std::string& text, size_t* last_len) {
  LineReader reader;
  int n = 0;
  for (char c : text) {
    if (reader.feed(c)) {
      n++;
      *last_len = reader.length();
    }
  }
  return n;
}

void test_cmd_without_cmd_is_dropped() {
  Config cfg;
  bool can_log = false;
  char reply[LINE_BUF] = {};
  const char* line = R"({"type":"cmd","key":"sim","value":false})";
  CmdResult r = handle_line(line, strlen(line), cfg, can_log, reply, sizeof(reply));
  TEST_ASSERT_FALSE(r.is_cmd);
  TEST_ASSERT_TRUE(cfg.sim);
}

void test_line_reader_limits() {
  size_t len = 0;
  std::string at_limit(MAX_LINE_BYTES, 'x');
  TEST_ASSERT_EQUAL(1, count_lines(at_limit + "\r\n", &len));  // kept, '\r' removed
  TEST_ASSERT_EQUAL(MAX_LINE_BYTES, len);
  TEST_ASSERT_EQUAL(1, count_lines(at_limit + "\n", &len));
  TEST_ASSERT_EQUAL(0, count_lines(at_limit + "y\n", &len));    // one byte too long
  TEST_ASSERT_EQUAL(0, count_lines(at_limit + "yy\r\n", &len));
  // Recovers on the next line after an over-long one.
  TEST_ASSERT_EQUAL(1, count_lines(std::string(5000, 'x') + "\n{}\n", &len));
  TEST_ASSERT_EQUAL(2, len);
}

void test_log_line() {
  char buf[LINE_BUF];
  size_t n = build_log("warn", "ble", "BMS disconnected, retrying", buf, sizeof(buf));
  JsonDocument got, want;
  deserializeJson(got, buf, n);
  deserializeJson(want, lines("log.jsonl")[1]);
  TEST_ASSERT_TRUE(same(got.as<JsonVariantConst>(), want.as<JsonVariantConst>()));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_state_full_matches_fixture);
  RUN_TEST(test_state_minimal_matches_fixture);
  RUN_TEST(test_state_stale_matches_fixture);
  RUN_TEST(test_staleness_is_decided_at_send_time);
  RUN_TEST(test_power_follows_pack);
  RUN_TEST(test_hello_matches_fixture);
  RUN_TEST(test_cmd_fixture_all_accepted);
  RUN_TEST(test_bad_cmds_answered_with_warn);
  RUN_TEST(test_garbage_fixture);
  RUN_TEST(test_cmd_without_cmd_is_dropped);
  RUN_TEST(test_line_reader_limits);
  RUN_TEST(test_log_line);
  return UNITY_END();
}
