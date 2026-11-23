package com.cartdash.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SpeedDeadBandTest {
    @Test fun holdsNearTheHalf() {
        val b = SpeedDeadBand()
        assertEquals(14, b.update(14.2))
        assertEquals(14, b.update(14.5))
        assertEquals(14, b.update(14.6))
        assertEquals(15, b.update(14.8))
        assertEquals(15, b.update(14.4))
        assertEquals(14, b.update(14.2))
    }

    @Test fun zeroAndMissing() {
        val b = SpeedDeadBand()
        assertEquals(1, b.update(1.0))
        assertEquals(0, b.update(0.4))
        assertNull(b.update(null))
        assertEquals(8, b.update(8.4))
    }

    @Test fun formatting() {
        assertEquals(DASH, fmt(null))
        assertEquals("66.4", fmt(66.44, 1))
        assertEquals("82", fmt(82.4))
    }
}
