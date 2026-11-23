#include "config_store.h"

#include <Preferences.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

namespace {
const char* NVS_NAMESPACE = "cartdash";
Config current;
SemaphoreHandle_t mutex = nullptr;
}  // namespace

namespace config_store {

void begin() {
  mutex = xSemaphoreCreateMutex();
  Preferences p;
  p.begin(NVS_NAMESPACE, true);
  Config c;
  c.wheel_dia_in = p.getFloat("wheel_dia_in", c.wheel_dia_in);
  c.gear_ratio = p.getFloat("gear_ratio", c.gear_ratio);
  c.pulses_per_rev = p.getFloat("pulses_rev", c.pulses_per_rev);
  c.speed_src_rpm = p.getBool("speed_rpm", c.speed_src_rpm);
  c.sim = p.getBool("sim", c.sim);
  p.end();
  current = c;
}

Config get() {
  xSemaphoreTake(mutex, portMAX_DELAY);
  Config c = current;
  xSemaphoreGive(mutex);
  return c;
}

void put(const Config& c) {
  xSemaphoreTake(mutex, portMAX_DELAY);
  current = c;
  xSemaphoreGive(mutex);
  Preferences p;
  p.begin(NVS_NAMESPACE, false);
  p.putFloat("wheel_dia_in", c.wheel_dia_in);
  p.putFloat("gear_ratio", c.gear_ratio);
  p.putFloat("pulses_rev", c.pulses_per_rev);
  p.putBool("speed_rpm", c.speed_src_rpm);
  p.putBool("sim", c.sim);
  p.end();
}

}  // namespace config_store
