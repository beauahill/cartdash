package com.cartdash.data

import org.junit.Assert.assertEquals
import org.junit.Test

class LineSplitterTest {
    private fun split(bytes: ByteArray, chunk: Int): List<ByteArray> {
        val out = ArrayList<ByteArray>()
        val s = LineSplitter()
        var i = 0
        while (i < bytes.size) {
            val n = minOf(chunk, bytes.size - i)
            s.feed(bytes.copyOfRange(i, i + n)) { out += it }
            i += n
        }
        return out
    }

    @Test fun garbageFixtureInAnyChunkSize() {
        val all = Fixtures.bytes("garbage.jsonl")
        for (chunk in listOf(1, 7, 64, 4096)) {
            val lines = split(all, chunk)
            assertEquals("chunk $chunk", 11, lines.size)  // the over-long line is dropped
            val kept = lines.mapNotNull { Protocol.parseLine(it) }
            assertEquals(3, kept.size)
        }
    }

    @Test fun lineAtTheLimitIsKept() {
        val body = "{\"type\":\"log\",\"msg\":\"" + "x".repeat(Protocol.MAX_LINE_BYTES - 23) + "\"}"
        assertEquals(Protocol.MAX_LINE_BYTES, body.length)
        val lines = split((body + "\r\n").toByteArray(), 100)
        assertEquals(1, lines.size)
        assertEquals(true, Protocol.parseLine(lines[0]) is Message.Log)
    }

    @Test fun recoversAfterOverlongLine() {
        val text = "x".repeat(5000) + "\n" + "{\"type\":\"hello\",\"proto\":1,\"fw\":\"a\",\"uptime_s\":1}\n"
        val lines = split(text.toByteArray(), 333)
        assertEquals(1, lines.size)
    }
}
