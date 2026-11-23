#include "state.h"

#include <string.h>

#include "config.h"

#if defined(ARDUINO)
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#else
#include <mutex>
#endif

const FieldInfo FIELD_INFO[FIELD_COUNT] = {
    {"speed_mph", K_NUM, 1},
    {"gear", K_GEAR, 0},
    {"speed_mode", K_TEXT, 0},
    {"soc_pct", K_NUM, 0},
    {"pack_v", K_NUM, 2},
    {"pack_a", K_NUM, 1},
    {"power_kw", K_NUM, 2},
    {"cell_v_min", K_NUM, 3},
    {"cell_v_max", K_NUM, 3},
    {"bms_temp_f", K_TEMPS, 0},
    {"ctrl_temp_f", K_NUM, 0},
    {"motor_temp_f", K_NUM, 0},
    {"motor_rpm", K_NUM, 0},
    {"turn_left", K_BOOL, 0},
    {"turn_right", K_BOOL, 0},
    {"low_beam", K_BOOL, 0},
    {"high_beam", K_BOOL, 0},
    {"brake", K_BOOL, 0},
    {"park_brake", K_BOOL, 0},
    {"reverse", K_BOOL, 0},
    {"illum", K_BOOL, 0},
    {"kelly_faults", K_FAULTS, 0},
    {"bms_faults", K_FAULTS, 0},
};

Field field_by_name(const char* name) {
  for (uint8_t i = 0; i < FIELD_COUNT; i++) {
    if (strcmp(FIELD_INFO[i].name, name) == 0) return static_cast<Field>(i);
  }
  return FIELD_COUNT;
}

bool Snapshot::is_stale(Field f, uint32_t now_ms) const {
  // Unsigned subtraction stays right when millis() wraps.
  return has[f] && static_cast<uint32_t>(now_ms - updated_ms[f]) > STALE_AFTER_MS;
}

State::State() {
#if defined(ARDUINO)
  mutex_ = xSemaphoreCreateMutex();
#else
  mutex_ = new std::mutex();
#endif
}

State::~State() {
#if defined(ARDUINO)
  vSemaphoreDelete(static_cast<SemaphoreHandle_t>(mutex_));
#else
  delete static_cast<std::mutex*>(mutex_);
#endif
}

void State::lock() const {
#if defined(ARDUINO)
  xSemaphoreTake(static_cast<SemaphoreHandle_t>(mutex_), portMAX_DELAY);
#else
  static_cast<std::mutex*>(mutex_)->lock();
#endif
}

void State::unlock() const {
#if defined(ARDUINO)
  xSemaphoreGive(static_cast<SemaphoreHandle_t>(mutex_));
#else
  static_cast<std::mutex*>(mutex_)->unlock();
#endif
}

void State::touch(Field f, uint32_t now_ms) {
  s_.has[f] = true;
  s_.updated_ms[f] = now_ms;
}

void State::set_num(Field f, float value, uint32_t now_ms) {
  if (f >= FIELD_COUNT || FIELD_INFO[f].kind != K_NUM) return;
  lock();
  s_.num[f] = value;
  touch(f, now_ms);
  unlock();
}

void State::set_bool(Field f, bool value, uint32_t now_ms) {
  if (f >= FIELD_COUNT || FIELD_INFO[f].kind != K_BOOL) return;
  lock();
  s_.flag[f] = value;
  touch(f, now_ms);
  unlock();
}

void State::set_gear(char gear, uint32_t now_ms) {
  if (gear != 'D' && gear != 'N' && gear != 'R') return;
  lock();
  s_.gear = gear;
  touch(F_GEAR, now_ms);
  unlock();
}

void State::set_speed_mode(const char* mode, uint32_t now_ms) {
  lock();
  strncpy(s_.speed_mode, mode, TEXT_LEN - 1);
  s_.speed_mode[TEXT_LEN - 1] = '\0';
  touch(F_SPEED_MODE, now_ms);
  unlock();
}

void State::set_bms_temps(const float* temps, size_t count, uint32_t now_ms) {
  if (count > MAX_TEMPS) count = MAX_TEMPS;
  lock();
  for (size_t i = 0; i < count; i++) s_.temps[i] = temps[i];
  s_.temp_count = static_cast<uint8_t>(count);
  touch(F_BMS_TEMP_F, now_ms);
  unlock();
}

void State::set_faults(Field f, const char* const* codes, size_t count, uint32_t now_ms) {
  if (f != F_KELLY_FAULTS && f != F_BMS_FAULTS) return;
  if (count > MAX_FAULTS) count = MAX_FAULTS;
  lock();
  Faults& out = (f == F_KELLY_FAULTS) ? s_.kelly_faults : s_.bms_faults;
  for (size_t i = 0; i < count; i++) {
    strncpy(out.code[i], codes[i], FAULT_LEN - 1);
    out.code[i][FAULT_LEN - 1] = '\0';
  }
  out.count = static_cast<uint8_t>(count);
  touch(f, now_ms);
  unlock();
}

void State::set_pack(float volts, float amps, uint32_t now_ms) {
  lock();
  s_.num[F_PACK_V] = volts;
  s_.num[F_PACK_A] = amps;
  s_.num[F_POWER_KW] = volts * amps / 1000.0f;
  touch(F_PACK_V, now_ms);
  touch(F_PACK_A, now_ms);
  touch(F_POWER_KW, now_ms);
  unlock();
}

void State::clear(Field f) {
  if (f >= FIELD_COUNT) return;
  lock();
  s_.has[f] = false;
  unlock();
}

void State::snapshot(Snapshot& out) const {
  lock();
  out = s_;
  unlock();
}
