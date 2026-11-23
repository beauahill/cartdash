// Cart Dash ESP32-S3 firmware. Each job runs in its own FreeRTOS task and
// writes to the shared State; usb_link streams it to the head unit.
#include <Arduino.h>
#include <esp_task_wdt.h>

#include "config.h"
#include "config_store.h"
#include "sim.h"
#include "state.h"
#include "usb_link.h"

namespace {

State g_state;

void sim_task(void*) {
  esp_task_wdt_add(nullptr);
  static Sim sim;
  TickType_t wake = xTaskGetTickCount();
  for (;;) {
    Config cfg = config_store::get();
    // With sim off and no hardware inputs yet (Phase 0), fields go stale and
    // then show "--" in the app, which is the honest answer.
    if (cfg.sim) sim.step(millis(), cfg, g_state);
    esp_task_wdt_reset();
    vTaskDelayUntil(&wake, pdMS_TO_TICKS(SIM_PERIOD_MS));
  }
}

void start_watchdog() {
  esp_task_wdt_config_t wdt = {};
  wdt.timeout_ms = TASK_WDT_TIMEOUT_MS;
  wdt.idle_core_mask = 0;
  wdt.trigger_panic = true;
  // The Arduino core may have started the watchdog already.
  if (esp_task_wdt_init(&wdt) != ESP_OK) esp_task_wdt_reconfigure(&wdt);
}

}  // namespace

void setup() {
  start_watchdog();
  config_store::begin();
  usb_link::begin(g_state);
  xTaskCreate(sim_task, "sim", STACK_SIM, nullptr, PRIO_SIM, nullptr);
}

void loop() {
  // All work happens in tasks.
  vTaskDelete(nullptr);
}
