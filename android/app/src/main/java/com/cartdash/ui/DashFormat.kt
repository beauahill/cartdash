package com.cartdash.ui

import kotlin.math.abs
import kotlin.math.roundToInt

/** Text shown for a missing, null, or stale reading. */
const val DASH = "--"

/**
 * Whole mph with a small dead band, so the big number does not flicker
 * between two values when the speed sits near a half.
 */
class SpeedDeadBand(private val band: Double = 0.7) {
    private var shown: Int? = null

    fun update(mph: Double?): Int? {
        if (mph == null) {
            shown = null
            return null
        }
        val current = shown
        val next = when {
            mph < 0.5 -> 0
            current == null -> mph.roundToInt()
            abs(mph - current) >= band -> mph.roundToInt()
            else -> current
        }
        shown = next
        return next
    }
}

fun fmt(value: Double?, decimals: Int = 0): String =
    if (value == null) DASH else if (decimals == 0) value.roundToInt().toString() else "%.${decimals}f".format(value)
