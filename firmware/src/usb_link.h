// USB CDC link to the head unit: state and hello out, cmd lines in. Arduino only.
#pragma once

#include "state.h"

namespace usb_link {
void begin(State& state);  // opens the port and starts the send and cmd tasks
bool can_log_on();
}  // namespace usb_link
