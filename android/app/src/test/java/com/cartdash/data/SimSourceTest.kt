package com.cartdash.data

import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SimSourceTest {
    @Test fun simLinesParseAndCoverTheDash() = runTest {
        // 100 s of simulated time: 1000 states plus 101 hellos (seconds 0 to 100).
        val msgs = SimSource().lines().take(1101).toList().map { line ->
            assertTrue(line.size <= Protocol.MAX_LINE_BYTES)
            requireNotNull(Protocol.parseLine(line)) { String(line) }
        }
        val states = msgs.filterIsInstance<Message.State>().map { it.state }
        assertEquals(1000, states.size)
        assertEquals((0L until 1000L).toList(), states.map { it.seq })
        assertTrue(msgs.filterIsInstance<Message.HelloMsg>().all { it.hello.sim == true })
        assertTrue(states.any { it.turnLeft == true } && states.any { it.turnRight == true })
        assertTrue(states.any { it.gear == "R" })
        assertTrue(states.any { it.illum == true } && states.any { it.illum == false })
        assertTrue("Kelly dropout goes stale", states.any { "motor_temp_f" in it.stale && it.motorTempF == null })
        assertTrue(states.first().socPct == null && states.last().socPct != null)
    }
}
