#include "usb_link.h"

#include <Arduino.h>
#include <esp_task_wdt.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

#include "config.h"
#include "config_store.h"
#include "protocol.h"

namespace {

State* g_state = nullptr;
SemaphoreHandle_t g_write_mutex = nullptr;  // both tasks write to the port
volatile bool g_can_log = false;

// Write one whole line. The short TX timeout set in begin() means a host that
// stops reading costs at most a few ms per line, never a stall.
void write_line(const char* line, size_t len) {
  if (len == 0) return;
  xSemaphoreTake(g_write_mutex, portMAX_DELAY);
  Serial.write(reinterpret_cast<const uint8_t*>(line), len);
  xSemaphoreGive(g_write_mutex);
}

void send_task(void*) {
  esp_task_wdt_add(nullptr);
  static char buf[LINE_BUF];
  static Snapshot snap;
  uint32_t seq = 0;
  uint32_t last_hello = 0;
  bool first = true;
  bool was_connected = false;
  TickType_t wake = xTaskGetTickCount();
  for (;;) {
    uint32_t now = millis();
    bool connected = static_cast<bool>(Serial);
    // hello right away at boot and whenever the port opens, then once a second.
    if (first || (connected && !was_connected) || now - last_hello >= HELLO_PERIOD_MS) {
      first = false;
      last_hello = now;
      write_line(buf, build_hello(now / 1000, config_store::get().sim, buf, sizeof(buf)));
    }
    was_connected = connected;

    g_state->snapshot(snap);  // copy under the lock, build JSON outside it
    write_line(buf, build_state(snap, seq++, now, buf, sizeof(buf)));

    esp_task_wdt_reset();
    vTaskDelayUntil(&wake, pdMS_TO_TICKS(STATE_PERIOD_MS));
  }
}

void cmd_task(void*) {
  static LineReader reader;
  static char reply[LINE_BUF];
  for (;;) {
    while (Serial.available() > 0) {
      if (!reader.feed(static_cast<char>(Serial.read()))) continue;
      Config cfg = config_store::get();
      bool can_log = g_can_log;
      CmdResult r = handle_line(reader.line(), reader.length(), cfg, can_log, reply, sizeof(reply));
      if (!r.is_cmd) continue;
      if (r.config_changed) config_store::put(cfg);
      if (r.can_log_changed) g_can_log = can_log;
      write_line(reply, strlen(reply));
    }
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

}  // namespace

namespace usb_link {

void begin(State& state) {
  g_state = &state;
  g_write_mutex = xSemaphoreCreateMutex();
  Serial.setTxTimeoutMs(USB_TX_TIMEOUT_MS);
  Serial.begin(115200);  // the rate does not matter on native USB
  xTaskCreate(send_task, "usb_send", STACK_USB_SEND, nullptr, PRIO_USB_SEND, nullptr);
  xTaskCreate(cmd_task, "usb_cmd", STACK_USB_CMD, nullptr, PRIO_USB_CMD, nullptr);
}

bool can_log_on() { return g_can_log; }

}  // namespace usb_link
