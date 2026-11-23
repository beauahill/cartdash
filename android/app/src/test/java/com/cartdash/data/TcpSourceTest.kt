package com.cartdash.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.ServerSocket

/** TcpSource against a local server standing in for tools/fake_esp.py. */
class TcpSourceTest {
    @Test fun readsLinesReconnectsAndSends() = runBlocking {
        ServerSocket(0).use { server ->
            val src = TcpSource("127.0.0.1", server.localPort)
            val got = async(Dispatchers.IO) { src.lines().take(3).toList().map { String(it) } }

            // First connection: two lines split across writes and a \r\n ending, then the server hangs up.
            server.accept().use { c ->
                c.getOutputStream().apply {
                    write("{\"type\":\"hello\",\"proto\":1,".toByteArray())
                    write("\"fw\":\"a\",\"uptime_s\":1}\r\n{\"type\":\"st".toByteArray())
                    write("ate\",\"seq\":1,\"t\":2}\n".toByteArray())
                    flush()
                }
            }
            // The source reconnects on its own.
            server.soTimeout = 10_000
            server.accept().use { c ->
                c.getOutputStream().apply { write("{\"type\":\"state\",\"seq\":2,\"t\":3}\n".toByteArray()); flush() }
                val lines = withTimeout(10_000) { got.await() }
                assertEquals(3, lines.size)
                assertTrue(Protocol.parseLine(lines[0]) is Message.HelloMsg)
                assertEquals(2L, (Protocol.parseLine(lines[2]) as Message.State).state.seq)
            }
        }
    }

    @Test fun sendReachesTheServer() = runBlocking {
        ServerSocket(0).use { server ->
            server.soTimeout = 10_000
            val src = TcpSource("127.0.0.1", server.localPort)
            val reader = launch(Dispatchers.IO) { src.lines().collect {} }
            server.accept().use { c ->
                c.getOutputStream().apply { write("{\"type\":\"hello\",\"proto\":1,\"fw\":\"a\",\"uptime_s\":1}\n".toByteArray()); flush() }
                // Wait until the source is connected, then send.
                val cmd = "{\"type\":\"cmd\",\"cmd\":\"can_log\",\"on\":true}"
                withTimeout(10_000) {
                    while (true) {
                        src.send(cmd)
                        if (c.getInputStream().available() > 0) break
                        kotlinx.coroutines.delay(50)
                    }
                }
                val line = c.getInputStream().bufferedReader().readLine()
                assertEquals(cmd, line)
            }
            // Cancelling ends a blocked read promptly, not after the 5 s read timeout.
            val t0 = System.nanoTime()
            reader.cancel()
            withTimeout(2_000) { reader.join() }
            assertTrue((System.nanoTime() - t0) / 1_000_000 < 2_000)
        }
    }
}
