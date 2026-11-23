// Simulated cart, so the firmware streams believable data before any cart
// hardware is connected. Follows tools/fake_esp.py's drive scenario: a 60 s
// loop of pull away, cruise, blinkers, regen, brake, park, and reverse, with
// every other loop at night. Kelly data drops out for a while every 90 s and
// the BMS only appears 1.5 s after boot, so the app's "--" path gets used.
// No Arduino headers.
#pragma once

#include <stdint.h>

#include "logic.h"
#include "protocol.h"
#include "state.h"

class Sim {
 public:
  explicit Sim(uint32_t seed = 1) : rng_(seed) {}

  // Advance the model to now_ms and write every field that is "online".
  void step(uint32_t now_ms, const Config& cfg, State& state);

  // True while the simulated Kelly is silent (its fields go stale).
  static bool kelly_online(uint32_t now_ms);
  static bool bms_online(uint32_t now_ms);

 private:
  float uniform(float lo, float hi);

  uint32_t rng_;
  bool started_ = false;
  uint32_t last_ms_ = 0;
  float soc_ = 82.0f;
  float ctrl_temp_ = 95.0f;
  float motor_temp_ = 105.0f;
  BlinkerLatch left_;
  BlinkerLatch right_;
};
