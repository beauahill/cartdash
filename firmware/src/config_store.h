// Config kept in NVS and shared between tasks behind a mutex. Arduino only.
#pragma once

#include "protocol.h"

namespace config_store {
void begin();             // load from NVS, or defaults on first boot
Config get();             // a copy, safe from any task
void put(const Config&);  // apply now and save to NVS
}  // namespace config_store
