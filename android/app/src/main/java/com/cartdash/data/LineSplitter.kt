package com.cartdash.data

import java.io.ByteArrayOutputStream

/**
 * Splits a received byte stream into lines. A line longer than
 * [Protocol.MAX_LINE_BYTES] is dropped up to the next newline, without
 * holding it in memory. Lines are returned without the newline.
 */
class LineSplitter(private val maxBytes: Int = Protocol.MAX_LINE_BYTES) {
    private val buf = ByteArrayOutputStream(256)
    private var overflow = false

    fun feed(bytes: ByteArray, count: Int = bytes.size, onLine: (ByteArray) -> Unit) {
        for (i in 0 until count) {
            val b = bytes[i]
            if (b == '\n'.code.toByte()) {
                if (!overflow) onLine(buf.toByteArray())
                buf.reset()
                overflow = false
            } else if (!overflow) {
                // Allow one extra byte for a '\r' before the newline.
                if (buf.size() >= maxBytes + 1) {
                    overflow = true
                    buf.reset()
                } else {
                    buf.write(b.toInt())
                }
            }
        }
    }
}
