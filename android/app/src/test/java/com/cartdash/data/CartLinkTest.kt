package com.cartdash.data

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class CartLinkTest {
    private class FakeSource : DataSource {
        override val label = "FAKE"
        val ch = Channel<ByteArray>(Channel.UNLIMITED)
        override fun lines(): Flow<ByteArray> = ch.receiveAsFlow()
        override suspend fun send(line: String) {}
    }

    private fun TestScope.link(src: FakeSource) =
        CartLink(backgroundScope, { testScheduler.currentTime }) { src }

    @Test fun linkUpOnAnyLineAndLostAfterOneSecond() = runTest {
        val src = FakeSource()
        val link = link(src)
        link.start(SourceKind.TCP)
        runCurrent()
        assertFalse(link.snapshot.value.linkUp)

        src.ch.send(Fixtures.lines("state_full.jsonl")[0])
        runCurrent()
        assertTrue(link.snapshot.value.linkUp)
        assertNotNull(link.snapshot.value.state)

        advanceTimeBy(900)
        src.ch.send(Fixtures.lines("log.jsonl")[0])  // a log line keeps the link alive
        runCurrent()
        advanceTimeBy(900)
        assertTrue(link.snapshot.value.linkUp)

        advanceTimeBy(300)  // 1.2 s since the last line
        assertFalse(link.snapshot.value.linkUp)
        assertNull("no stale numbers while the link is lost", link.snapshot.value.state)
    }

    @Test fun garbageLinesStillCountAsTraffic() = runTest {
        val src = FakeSource()
        val link = link(src)
        link.start(SourceKind.TCP)
        for (line in Fixtures.lines("garbage.jsonl")) src.ch.send(line)
        runCurrent()
        val s = link.snapshot.value
        assertTrue(s.linkUp)
        assertEquals(3L, s.state!!.seq)
        assertEquals(12L, s.lines)
    }

    @Test fun simFlagFromHello() = runTest {
        val src = FakeSource()
        val link = link(src)
        link.start(SourceKind.TCP)
        assertFalse(link.snapshot.value.sim)
        src.ch.send(Fixtures.lines("hello.jsonl")[0])
        runCurrent()
        assertTrue(link.snapshot.value.sim)
    }
}
