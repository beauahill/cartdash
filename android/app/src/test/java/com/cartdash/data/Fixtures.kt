package com.cartdash.data

import java.io.File

/** The shared samples in protocol/fixtures; Gradle passes their path. */
object Fixtures {
    private val dir = File(requireNotNull(System.getProperty("cartdash.fixtures")) { "cartdash.fixtures not set" })

    fun bytes(name: String): ByteArray = File(dir, name).readBytes()

    /** Lines split on '\n' only, like tools/tests/test_protocol.py, so a '\r' stays. */
    fun lines(name: String): List<ByteArray> {
        val all = bytes(name)
        val out = ArrayList<ByteArray>()
        var start = 0
        for (i in all.indices) {
            if (all[i] == '\n'.code.toByte()) {
                out += all.copyOfRange(start, i)
                start = i + 1
            }
        }
        return out
    }
}
