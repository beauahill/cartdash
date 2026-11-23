package com.cartdash.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Port of tools/tests/test_protocol.py's receiver checks, on the same fixtures. */
class ProtocolTest {
    private fun state(name: String) = (Protocol.parseLine(Fixtures.lines(name)[0]) as Message.State).state

    @Test fun cleanFixturesParse() {
        for (name in listOf("state_full.jsonl", "state_minimal.jsonl", "state_stale.jsonl", "hello.jsonl", "log.jsonl", "unknown.jsonl", "cmd.jsonl")) {
            for (raw in Fixtures.lines(name)) assertNotNull("$name: ${String(raw)}", Protocol.parseLine(raw))
        }
    }

    @Test fun garbageFixture() {
        val raw = Fixtures.lines("garbage.jsonl")
        assertEquals(12, raw.size)
        val kept = raw.mapIndexedNotNull { i, r ->
            when (val m = Protocol.parseLine(r)) {
                null -> null
                is Message.State -> Triple(i + 1, "state", m.state.seq)
                is Message.HelloMsg -> Triple(i + 1, "hello", null)
                else -> Triple(i + 1, m.toString(), null)
            }
        }
        assertEquals(listOf(Triple(1, "hello", null), Triple(8, "state", 2L), Triple(12, "state", 3L)), kept)
        assertEquals('\r'.code.toByte(), raw[11].last())
        assertTrue(raw[10].size > Protocol.MAX_LINE_BYTES)
    }

    @Test fun stateFullParsesEveryField() {
        val s = state("state_full.jsonl")
        assertEquals(1042L, s.seq)
        assertEquals(1234567L, s.t)
        assertEquals(14.2, s.speedMph!!, 0.0)
        assertEquals("D", s.gear)
        assertEquals("high", s.speedMode)
        assertEquals(82.0, s.socPct!!, 0.0)
        assertEquals(66.4, s.packV!!, 0.0)
        assertEquals(-48.5, s.packA!!, 0.0)
        assertEquals(-3.2, s.powerKw!!, 0.0)
        assertEquals(3.311, s.cellVMin!!, 0.0)
        assertEquals(3.324, s.cellVMax!!, 0.0)
        assertEquals(listOf(78.0, 80.0), s.bmsTempF)
        assertEquals(104.0, s.ctrlTempF!!, 0.0)
        assertNull("motor_temp_f is stale", s.motorTempF)
        assertEquals(2210.0, s.motorRpm!!, 0.0)
        assertEquals(false, s.turnLeft)
        assertEquals(true, s.turnRight)
        assertEquals(true, s.lowBeam)
        assertEquals(false, s.highBeam)
        assertEquals(false, s.brake)
        assertEquals(false, s.parkBrake)
        assertEquals(false, s.reverse)
        assertEquals(true, s.illum)
        assertEquals(emptyList<String>(), s.kellyFaults)
        assertEquals(emptyList<String>(), s.bmsFaults)
        assertFalse(s.regenWarning)
    }

    @Test fun staleAndNullFieldsShowDashes() {
        val s = state("state_stale.jsonl")
        assertNull(s.socPct)
        assertNull(s.packV)
        assertNull(s.packA)
        assertNull(s.powerKw)
        assertNull(s.motorTempF)
        assertNull("null", s.ctrlTempF)
        assertEquals(0.0, s.speedMph!!, 0.0)
        assertEquals("N", s.gear)
        assertEquals(0.0, s.motorRpm!!, 0.0)
        assertEquals(listOf("cell_uv"), s.bmsFaults)

        val m = state("state_minimal.jsonl")
        assertEquals(0L, m.seq)
        assertNull(m.socPct)
        assertNull(m.speedMph)
        assertNull(m.turnLeft)
        assertNull(m.bmsFaults)
    }

    @Test fun helloFixture() {
        val h = (Protocol.parseLine(Fixtures.lines("hello.jsonl")[0]) as Message.HelloMsg).hello
        assertEquals(1L, h.proto)
        assertEquals(true, h.sim)
        assertEquals(120L, h.uptimeS)
    }

    @Test fun logFixture() {
        val logs = Fixtures.lines("log.jsonl").map { (Protocol.parseLine(it) as Message.Log).log }
        assertEquals(4, logs.size)
        assertEquals("18FF50E5#0102030405060708", logs[2].frame)
        assertEquals("123#", logs[3].frame)
        assertNull(logs[3].msg)
    }

    @Test fun unknownTypesAndFieldsIgnored() {
        val msgs = Fixtures.lines("unknown.jsonl").map { Protocol.parseLine(it) }
        val s = (msgs[0] as Message.State).state
        assertEquals(3.5, s.speedMph!!, 0.0)
        assertEquals("D", s.gear)
        assertEquals(Message.Unknown("telemetry2"), msgs[1])
        assertEquals("9.9.9", (msgs[2] as Message.HelloMsg).hello.fw)
    }

    @Test fun boolIsNotAnInt() {
        assertNull(Protocol.parseLine("""{"type":"state","seq":true,"t":1}"""))
        assertNull(Protocol.parseLine("""{"type":"state","seq":1.0,"t":1}"""))
        assertNull(Protocol.parseLine("""{"type":"state","seq":"1","t":1}"""))
    }

    @Test fun wrongTypedOptionalFieldIsMissing() {
        val s = (Protocol.parseLine("""{"type":"state","seq":1,"t":2,"speed_mph":"fast","brake":1,"gear":"P","soc_pct":true,"bms_temp_f":[1,"x"]}""") as Message.State).state
        assertNull(s.speedMph)
        assertNull(s.brake)
        assertNull(s.gear)
        assertNull(s.socPct)
        assertNull(s.bmsTempF)
    }

    @Test fun seqAndTWrapAt32Bits() {
        val s = (Protocol.parseLine("""{"type":"state","seq":4294967295,"t":4294967295}""") as Message.State).state
        assertEquals(4294967295L, s.seq)
        assertEquals(4294967295L, s.t)
    }

    @Test fun logNeedsMsgOrFrame() {
        assertNull(Protocol.parseLine("""{"type":"log","lvl":"info"}"""))
    }

    @Test fun invalidUtf8Dropped() {
        val bad = """{"type":"hello","proto":1,"fw":"x","uptime_s":1}""".toByteArray().also { it[30] = 0xFF.toByte() }
        assertNull(Protocol.parseLine(bad))
    }

    @Test fun regenWarning() {
        val s = CartState(seq = 0, t = 0, packA = 30.0, packV = 71.6, speedMph = 12.0)
        assertTrue(s.regenWarning)
        assertFalse(s.copy(packV = 70.9).regenWarning)
        assertFalse(s.copy(packA = -5.0).regenWarning)
        assertFalse("charger while parked", s.copy(speedMph = 0.0).regenWarning)
        assertFalse(s.copy(packV = null).regenWarning)
    }
}
