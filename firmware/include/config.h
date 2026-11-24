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

// Pin map for the Waveshare ESP32-S3-Zero (docs/wiring.md, docs/pinout.md).
// Every input comes through an opto that pulls the pin low while the cart
// signal is on, so inputs use the internal pull-up and read active low.
// Avoid: 0, 3, 45, 46 (strapping), 19 and 20 (USB), 26 to 32 (in-package flash
// and PSRAM), 43 and 44 (UART0, kept free for a debug serial).
#define INPUT_ACTIVE_LOW true
#define PIN_ACC 1              // left edge
#define PIN_TURN_LEFT 2        // left edge
#define PIN_TURN_RIGHT 4       // left edge
#define PIN_HEADLIGHTS 5       // left edge, low beam and illum
#define PIN_FORWARD 6          // left edge
#define PIN_SPEED_PULSE 7      // right edge, 6N137, pulse counter (PCNT)
#define PIN_BRAKE 8            // right edge
#define PIN_PARK_BRAKE 9       // right edge
#define PIN_HIGH_BEAM 10       // right edge
#define PIN_REVERSE 11         // right edge
#define PIN_SPEED_MODE 12      // right edge
#define PIN_CAN_TX 14          // top side pad, to the isolated transceiver (Phase 4)
#define PIN_CAN_RX 15          // top side pad
#define PIN_STATUS_LED 21      // onboard WS2812 RGB LED
// Spare: 13 (right edge), 16 (top side pad), 17, 18, 38 to 42 (bottom pads).
