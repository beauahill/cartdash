// Blinker latch, speed math, and the simulator.
#include <unity.h>

#include "config.h"
#include "logic.h"
#include "sim.h"
#include "state.h"

void test_blinker_latch_holds_between_flashes() {
  BlinkerLatch b;
  TEST_ASSERT_FALSE(b.flashing(0));
  b.update(true, 1000);
  TEST_ASSERT_TRUE(b.flashing(1000));
  b.update(true, 1300);  // no change: not a toggle
  TEST_ASSERT_TRUE(b.flashing(1000 + BLINKER_HOLD_MS));
  TEST_ASSERT_FALSE(b.flashing(1001 + BLINKER_HOLD_MS));
  b.update(false, 3000);
  TEST_ASSERT_TRUE(b.flashing(3500));
  TEST_ASSERT_FALSE(b.flashing(3000 + BLINKER_HOLD_MS + 1));
}

void test_blinker_steady_line_is_not_flashing() {
  BlinkerLatch b;
  b.update(true, 100);
  TEST_ASSERT_FALSE(b.flashing(5000));  // stuck on: one toggle long ago
}

void test_blinker_survives_millis_wrap() {
  BlinkerLatch b;
  b.update(true, 0xFFFFFF00u);
  TEST_ASSERT_TRUE(b.flashing(0x00000100u));
}

void test_speed_from_rpm() {
  // 22 in tire, 12:1, 15 mph -> wheel 229.2 rpm -> motor 2750 rpm
  float rpm = 15.0f * 63360.0f / 60.0f / (3.14159265f * 22.0f) * 12.0f;
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 15.0f, mph_from_motor_rpm(rpm, 12.0f, 22.0f));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 15.0f, mph_from_motor_rpm(-rpm, 12.0f, 22.0f));
  TEST_ASSERT_EQUAL_FLOAT(0.0f, mph_from_motor_rpm(rpm, 0.0f, 22.0f));
}

void test_speed_from_pulses() {
  // 4 pulses per turn, 22 in tire: 1 turn per second is 3.927 mph
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 3.927f, mph_from_pulse_hz(4.0f, 4.0f, 22.0f));
  TEST_ASSERT_EQUAL_FLOAT(0.0f, mph_from_pulse_hz(4.0f, 0.0f, 22.0f));
}

void test_sim_fills_fields_and_drops_them() {
  State st;
  Sim sim;
  Config cfg;
  Snapshot s;
  sim.step(100, cfg, st);
  st.snapshot(s);
  TEST_ASSERT_TRUE(s.has[F_SPEED_MPH]);
  TEST_ASSERT_FALSE(s.has[F_SOC_PCT]);  // BMS not connected yet
  TEST_ASSERT_FALSE(s.has[F_MOTOR_RPM]);
  bool saw_left = false, saw_right = false, saw_reverse = false, saw_regen = false, saw_stale = false;
  for (uint32_t t = 200; t <= 120000; t += 100) {
    sim.step(t, cfg, st);
    st.snapshot(s);
    saw_left |= s.flag[F_TURN_LEFT];
    saw_right |= s.flag[F_TURN_RIGHT];
    saw_reverse |= s.flag[F_REVERSE] && s.gear == 'R';
    saw_regen |= s.has[F_PACK_A] && s.num[F_PACK_A] > 0;
    if (s.is_stale(F_MOTOR_TEMP_F, t)) {
      saw_stale = true;
      TEST_ASSERT_FALSE(Sim::kelly_online(t));
      TEST_ASSERT_FALSE(s.is_stale(F_SOC_PCT, t));
    }
  }
  TEST_ASSERT_TRUE(s.has[F_SOC_PCT]);
  TEST_ASSERT_TRUE(saw_left && saw_right && saw_reverse && saw_regen && saw_stale);
}

void test_sim_blinker_is_steady_while_signalling() {
  State st;
  Sim sim;
  Config cfg;
  Snapshot s;
  // Right blinker is on from 18 s to 23 s of the loop; the relay flashes, the field does not.
  for (uint32_t t = 100; t <= 22000; t += 100) {
    sim.step(t, cfg, st);
    st.snapshot(s);
    if (t >= 18500 && t <= 22000) TEST_ASSERT_TRUE(s.flag[F_TURN_RIGHT]);
  }
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_blinker_latch_holds_between_flashes);
  RUN_TEST(test_blinker_steady_line_is_not_flashing);
  RUN_TEST(test_blinker_survives_millis_wrap);
  RUN_TEST(test_speed_from_rpm);
  RUN_TEST(test_speed_from_pulses);
  RUN_TEST(test_sim_fills_fields_and_drops_them);
  RUN_TEST(test_sim_blinker_is_steady_while_signalling);
  return UNITY_END();
}
