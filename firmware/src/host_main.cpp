// Host build only (pio run -e host): runs the simulator and the JSON builder
// on the laptop and prints the stream the ESP32 would send, so the stream can
// be checked with no board. tools/tests/test_firmware_stream.py reads it.
//
//   .pio/build/host/program [seconds]      simulated seconds, default 120
#include <stdio.h>
#include <stdlib.h>

#include "config.h"
#include "protocol.h"
#include "sim.h"
#include "state.h"

int main(int argc, char** argv) {
  double seconds = argc > 1 ? atof(argv[1]) : 120.0;
  uint32_t end_ms = static_cast<uint32_t>(seconds * 1000.0);
  State state;
  Sim sim;
  Config cfg;
  Snapshot snap;
  static char buf[LINE_BUF];
  uint32_t seq = 0;
  uint32_t last_hello = 0;
  bool first = true;
  for (uint32_t now = STATE_PERIOD_MS; now <= end_ms; now += STATE_PERIOD_MS) {
    sim.step(now, cfg, state);
    if (first || now - last_hello >= HELLO_PERIOD_MS) {
      first = false;
      last_hello = now;
      fwrite(buf, 1, build_hello(now / 1000, cfg.sim, buf, sizeof(buf)), stdout);
    }
    state.snapshot(snap);
    fwrite(buf, 1, build_state(snap, seq++, now, buf, sizeof(buf)), stdout);
  }
  return 0;
}
