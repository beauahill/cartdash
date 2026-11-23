#include "sim.h"

#include <math.h>

namespace {

constexpr float CELLS = 20.0f;
constexpr float PACK_AH = 130.0f;
constexpr float PACK_OHMS = 0.015f;
constexpr uint32_t KELLY_START_MS = 300;
constexpr uint32_t BMS_START_MS = 1500;
constexpr uint32_t KELLY_DROPOUT_EVERY_MS = 90000;
constexpr uint32_t KELLY_DROPOUT_FROM_MS = 70000;  // silent from 70 s to 75 s of every 90 s
constexpr uint32_t KELLY_DROPOUT_TO_MS = 75000;
constexpr uint32_t BLINK_HALF_PERIOD_MS = 350;      // the blinker relay toggles this often

// Resting LiFePO4 cell voltage by state of charge.
struct OcvPoint {
  float soc, volts;
};
constexpr OcvPoint OCV[] = {{0, 2.90f},  {5, 3.10f},  {10, 3.20f}, {20, 3.25f}, {40, 3.29f},
                            {60, 3.31f}, {80, 3.33f}, {90, 3.34f}, {100, 3.40f}};

float cell_ocv(float soc) {
  if (soc < 0) soc = 0;
  if (soc > 100) soc = 100;
  for (size_t i = 1; i < sizeof(OCV) / sizeof(OCV[0]); i++) {
    if (soc <= OCV[i].soc) {
      const OcvPoint& a = OCV[i - 1];
      const OcvPoint& b = OCV[i];
      return a.volts + (b.volts - a.volts) * (soc - a.soc) / (b.soc - a.soc);
    }
  }
  return OCV[sizeof(OCV) / sizeof(OCV[0]) - 1].volts;
}

struct Drive {
  float mph = 0.0f;
  float amps = -2.0f;
  char gear = 'D';
  bool brake = false, park = false, left = false, right = false, reverse = false;
};

// Driver inputs for a 60 s loop. tc is seconds into the loop.
Drive drive_cycle(float tc) {
  Drive d;
  if (tc < 2) {
    d.brake = true;
  } else if (tc < 12) {  // pull away
    d.mph = 15.0f * (tc - 2) / 10;
    d.amps = -60.0f - 6.0f * d.mph;
  } else if (tc < 30) {  // cruise, right blinker for a lane change
    d.mph = 15.0f + 0.4f * sinf(tc);
    d.amps = -(20.0f + 1.8f * d.mph);
    d.right = tc >= 18 && tc < 23;
  } else if (tc < 36) {  // lift off, regen
    d.mph = 15.0f - 7.0f * (tc - 30) / 6;
    d.amps = 18.0f;
  } else if (tc < 44) {  // slow cruise, left blinker to turn
    d.mph = 8.0f;
    d.amps = -(20.0f + 1.8f * 8.0f);
    d.left = tc >= 37 && tc < 42;
  } else if (tc < 50) {  // brake to a stop
    d.mph = 8.0f * (50 - tc) / 6;
    d.amps = 10.0f;
    d.brake = true;
  } else if (tc < 56) {  // parked
    d.park = tc >= 52;
    d.brake = tc < 52;
  } else if (tc < 59) {  // back up
    d.gear = 'R';
    d.reverse = true;
    d.mph = 2.0f;
    d.amps = -25.0f;
  }
  return d;
}

}  // namespace

bool Sim::kelly_online(uint32_t now_ms) {
  if (now_ms < KELLY_START_MS) return false;
  uint32_t in_cycle = now_ms % KELLY_DROPOUT_EVERY_MS;
  return !(in_cycle >= KELLY_DROPOUT_FROM_MS && in_cycle < KELLY_DROPOUT_TO_MS);
}

bool Sim::bms_online(uint32_t now_ms) { return now_ms >= BMS_START_MS; }

float Sim::uniform(float lo, float hi) {
  rng_ = rng_ * 1664525u + 1013904223u;  // small LCG, deterministic for tests
  return lo + (hi - lo) * static_cast<float>(rng_ >> 8) / static_cast<float>(1u << 24);
}

void Sim::step(uint32_t now_ms, const Config& cfg, State& state) {
  float dt = started_ ? static_cast<uint32_t>(now_ms - last_ms_) / 1000.0f : 0.0f;
  started_ = true;
  last_ms_ = now_ms;

  float t = now_ms / 1000.0f;
  float tc = fmodf(t, 60.0f);
  bool night = (now_ms / 60000u) % 2 == 1;
  Drive d = drive_cycle(tc);

  float amps = d.amps + uniform(-0.6f, 0.6f);
  soc_ += amps * dt / 3600.0f / PACK_AH * 100.0f;
  if (soc_ < 0) soc_ = 0;
  if (soc_ > 100) soc_ = 100;
  float pack_v = CELLS * cell_ocv(soc_) + amps * PACK_OHMS;
  float load = amps < 0 ? -amps : 0.0f;
  ctrl_temp_ += (95.0f + load * 0.12f - ctrl_temp_) * dt / 120.0f;
  motor_temp_ += (100.0f + load * 0.25f - motor_temp_) * dt / 300.0f;

  // The blinker lines flash like a relay; the latch turns that into a steady state.
  bool phase = (now_ms / BLINK_HALF_PERIOD_MS) % 2 == 0;
  left_.update(d.left && phase, now_ms);
  right_.update(d.right && phase, now_ms);

  float wheel_rpm = d.mph * 63360.0f / 60.0f / (3.14159265f * cfg.wheel_dia_in);
  float motor_rpm = wheel_rpm * cfg.gear_ratio;
  // Report speed the way the configured source would see it.
  float mph = cfg.speed_src_rpm ? mph_from_motor_rpm(motor_rpm, cfg.gear_ratio, cfg.wheel_dia_in) : d.mph;

  state.set_num(F_SPEED_MPH, mph, now_ms);
  state.set_gear(d.gear, now_ms);
  state.set_speed_mode("high", now_ms);
  state.set_bool(F_TURN_LEFT, left_.flashing(now_ms), now_ms);
  state.set_bool(F_TURN_RIGHT, right_.flashing(now_ms), now_ms);
  state.set_bool(F_LOW_BEAM, night, now_ms);
  state.set_bool(F_HIGH_BEAM, false, now_ms);
  state.set_bool(F_BRAKE, d.brake, now_ms);
  state.set_bool(F_PARK_BRAKE, d.park, now_ms);
  state.set_bool(F_REVERSE, d.reverse, now_ms);
  state.set_bool(F_ILLUM, night, now_ms);

  if (kelly_online(now_ms)) {
    state.set_num(F_CTRL_TEMP_F, ctrl_temp_, now_ms);
    state.set_num(F_MOTOR_TEMP_F, motor_temp_, now_ms);
    state.set_num(F_MOTOR_RPM, motor_rpm, now_ms);
    state.set_faults(F_KELLY_FAULTS, nullptr, 0, now_ms);
  }

  if (bms_online(now_ms)) {
    float cell = pack_v / CELLS;
    float spread = 0.004f + uniform(0.0f, 0.003f);
    state.set_num(F_SOC_PCT, soc_, now_ms);
    state.set_pack(pack_v, amps, now_ms);
    state.set_num(F_CELL_V_MIN, cell - spread / 2, now_ms);
    state.set_num(F_CELL_V_MAX, cell + spread / 2, now_ms);
    float temps[2] = {78.0f + roundf(load / 60.0f), 80.0f + roundf(load / 50.0f)};
    state.set_bms_temps(temps, 2, now_ms);
    state.set_faults(F_BMS_FAULTS, nullptr, 0, now_ms);
  }
}
