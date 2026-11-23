package com.cartdash.data

/**
 * One `state` message as the dash should show it (docs/usb_protocol.md).
 *
 * Every reading is nullable. Null means "show --": the field was missing,
 * null, the wrong type, or listed in `stale`. The UI has one way to show it.
 */
data class CartState(
    val seq: Long,
    val t: Long,
    val speedMph: Double? = null,
    val gear: String? = null,
    val speedMode: String? = null,
    val socPct: Double? = null,
    val packV: Double? = null,
    val packA: Double? = null,
    val powerKw: Double? = null,
    val cellVMin: Double? = null,
    val cellVMax: Double? = null,
    val bmsTempF: List<Double>? = null,
    val ctrlTempF: Double? = null,
    val motorTempF: Double? = null,
    val motorRpm: Double? = null,
    val turnLeft: Boolean? = null,
    val turnRight: Boolean? = null,
    val lowBeam: Boolean? = null,
    val highBeam: Boolean? = null,
    val brake: Boolean? = null,
    val parkBrake: Boolean? = null,
    val reverse: Boolean? = null,
    val illum: Boolean? = null,
    val kellyFaults: List<String>? = null,
    val bmsFaults: List<String>? = null,
    /** Names from the message's `stale` list, for display and debugging. */
    val stale: Set<String> = emptySet(),
) {
    /**
     * Regen into a nearly full pack. The BMS has a separate charge port, so
     * regen on the main leads has no overcharge protection (README, Motor
     * controller). Until the Kelly is decoded this uses BMS charge current
     * while moving, since charge current while parked is the charger.
     */
    val regenWarning: Boolean
        get() {
            val a = packA ?: return false
            val v = packV ?: return false
            return a > 0.0 && v > REGEN_WARN_VOLTS && (speedMph ?: 0.0) > REGEN_MIN_MPH
        }

    companion object {
        const val REGEN_WARN_VOLTS = 71.0
        const val REGEN_MIN_MPH = 2.0
    }
}

data class Hello(val proto: Long, val fw: String, val uptimeS: Long, val sim: Boolean?)

data class LogLine(val lvl: String?, val tag: String?, val msg: String?, val frame: String?, val t: Long?)
