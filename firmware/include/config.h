// Every pin, constant, and calibration default for the firmware.
// No magic numbers in source files: add them here.
#pragma once

#include <stdint.h>

#define FW_VERSION "0.1.0"
#define PROTO_VERSION 1

// USB link (docs/usb_protocol.md)
#define STATE_PERIOD_MS 100          // state lines at about 10 Hz
#define HELLO_PERIOD_MS 1000         // hello once a second
#define STALE_AFTER_MS 2000          // a field older than this is listed in "stale"
#define MAX_LINE_BYTES 2048          // longest line either side accepts
#define USB_TX_TIMEOUT_MS 5          // a host that stops reading must not stall us

// Blinkers report "flashing" while the line toggled within this window.
#define BLINKER_HOLD_MS 1200

// Simulator
#define SIM_PERIOD_MS 100

// Task watchdog. A hung task (for example the BLE stack later) resets the chip.
#define TASK_WDT_TIMEOUT_MS 5000

// FreeRTOS task priorities. USB send is the highest so the stream never stops.
#define PRIO_USB_SEND 5
#define PRIO_USB_CMD 4
#define PRIO_SIM 3
#define STACK_USB_SEND 8192
#define STACK_USB_CMD 8192
#define STACK_SIM 4096

// Calibration defaults. Placeholders until measured on the cart; the app sends
// the real values with set_config after every connect.
#define DEFAULT_WHEEL_DIA_IN 22.0f
#define DEFAULT_GEAR_RATIO 12.0f
#define DEFAULT_PULSES_PER_REV 1.0f
#define DEFAULT_SPEED_SRC_RPM true   // true: speed from Kelly motor RPM, false: factory pulse line
#define DEFAULT_SIM true             // Phase 0: no hardware inputs yet, so simulate

// Pin map for the N16R8 board, filled in from Phase 2.
// Avoid GPIO 35 to 37 (octal PSRAM), 19 and 20 (USB), and strapping pins 0, 3, 45, 46.
