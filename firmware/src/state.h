// Shared cart state: one value and one timestamp per field, behind a mutex.
// Data sources (simulator now, inputs, BMS, and Kelly later) write here.
// The USB task takes a snapshot and decides staleness at send time.
// No Arduino headers, so the native tests can use it.
#pragma once

#include <stddef.h>
#include <stdint.h>

// Order matches the field table in docs/usb_protocol.md.
enum Field : uint8_t {
  F_SPEED_MPH,
  F_GEAR,
  F_SPEED_MODE,
  F_SOC_PCT,
  F_PACK_V,
  F_PACK_A,
  F_POWER_KW,
  F_CELL_V_MIN,
  F_CELL_V_MAX,
  F_BMS_TEMP_F,
  F_CTRL_TEMP_F,
  F_MOTOR_TEMP_F,
  F_MOTOR_RPM,
  F_TURN_LEFT,
  F_TURN_RIGHT,
  F_LOW_BEAM,
  F_HIGH_BEAM,
  F_BRAKE,
  F_PARK_BRAKE,
  F_REVERSE,
  F_ILLUM,
  F_KELLY_FAULTS,
  F_BMS_FAULTS,
  FIELD_COUNT
};

enum FieldKind : uint8_t { K_NUM, K_BOOL, K_GEAR, K_TEXT, K_TEMPS, K_FAULTS };

struct FieldInfo {
  const char* name;  // JSON key
  FieldKind kind;
  int8_t decimals;   // K_NUM only: digits after the point on the wire, 0 sends an integer
};

extern const FieldInfo FIELD_INFO[FIELD_COUNT];

// Returns FIELD_COUNT if the name is not a state field.
Field field_by_name(const char* name);

constexpr size_t MAX_TEMPS = 4;
constexpr size_t MAX_FAULTS = 8;
constexpr size_t FAULT_LEN = 16;  // including the terminating zero
constexpr size_t TEXT_LEN = 8;

struct Faults {
  uint8_t count = 0;
  char code[MAX_FAULTS][FAULT_LEN] = {};
};

// A copy of every field, taken under the lock.
struct Snapshot {
  bool has[FIELD_COUNT] = {};        // false: never read, the field is left out
  uint32_t updated_ms[FIELD_COUNT] = {};
  float num[FIELD_COUNT] = {};       // K_NUM fields
  bool flag[FIELD_COUNT] = {};       // K_BOOL fields
  char gear = 'N';
  char speed_mode[TEXT_LEN] = {};
  uint8_t temp_count = 0;
  float temps[MAX_TEMPS] = {};
  Faults kelly_faults;
  Faults bms_faults;

  // True if the field has a reading older than STALE_AFTER_MS at now_ms.
  bool is_stale(Field f, uint32_t now_ms) const;
};

class State {
 public:
  State();
  ~State();
  State(const State&) = delete;
  State& operator=(const State&) = delete;

  void set_num(Field f, float value, uint32_t now_ms);
  void set_bool(Field f, bool value, uint32_t now_ms);
  void set_gear(char gear, uint32_t now_ms);  // 'D', 'N', or 'R'
  void set_speed_mode(const char* mode, uint32_t now_ms);
  void set_bms_temps(const float* temps, size_t count, uint32_t now_ms);
  void set_faults(Field f, const char* const* codes, size_t count, uint32_t now_ms);
  // Pack voltage and current together; power_kw follows from them.
  void set_pack(float volts, float amps, uint32_t now_ms);
  // Forget a field, as if it was never read.
  void clear(Field f);

  void snapshot(Snapshot& out) const;

 private:
  void lock() const;
  void unlock() const;
  void touch(Field f, uint32_t now_ms);

  Snapshot s_;
  void* mutex_;
};
