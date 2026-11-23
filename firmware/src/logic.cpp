#include "logic.h"

#include "config.h"

static constexpr float PI_F = 3.14159265f;
static constexpr float INCHES_PER_MILE = 63360.0f;

void BlinkerLatch::update(bool level, uint32_t now_ms) {
  if (level != level_) {
    level_ = level;
    toggled_ = true;
    last_toggle_ms_ = now_ms;
  }
}

bool BlinkerLatch::flashing(uint32_t now_ms) const {
  return toggled_ && static_cast<uint32_t>(now_ms - last_toggle_ms_) <= BLINKER_HOLD_MS;
}

static float mph_from_wheel_rps(float wheel_rps, float wheel_dia_in) {
  return wheel_rps * PI_F * wheel_dia_in * 3600.0f / INCHES_PER_MILE;
}

float mph_from_motor_rpm(float motor_rpm, float gear_ratio, float wheel_dia_in) {
  if (gear_ratio <= 0.0f || wheel_dia_in <= 0.0f) return 0.0f;
  float wheel_rps = motor_rpm / gear_ratio / 60.0f;
  if (wheel_rps < 0.0f) wheel_rps = -wheel_rps;  // speed is never negative; gear says the direction
  return mph_from_wheel_rps(wheel_rps, wheel_dia_in);
}

float mph_from_pulse_hz(float pulse_hz, float pulses_per_rev, float wheel_dia_in) {
  if (pulses_per_rev <= 0.0f || wheel_dia_in <= 0.0f || pulse_hz <= 0.0f) return 0.0f;
  return mph_from_wheel_rps(pulse_hz / pulses_per_rev, wheel_dia_in);
}
