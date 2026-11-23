// Small pure helpers: blinker latch and speed math. No Arduino headers.
#pragma once

#include <stdint.h>

// A blinker line flashes on and off. The dash wants one steady "flashing"
// state: true while the line toggled within the last BLINKER_HOLD_MS.
class BlinkerLatch {
 public:
  void update(bool level, uint32_t now_ms);
  bool flashing(uint32_t now_ms) const;

 private:
  bool level_ = false;
  bool toggled_ = false;
  uint32_t last_toggle_ms_ = 0;
};

// Road speed from Kelly motor RPM.
float mph_from_motor_rpm(float motor_rpm, float gear_ratio, float wheel_dia_in);

// Road speed from the factory speed pulse line.
float mph_from_pulse_hz(float pulse_hz, float pulses_per_rev, float wheel_dia_in);
