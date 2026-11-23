package com.cartdash.data

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import java.io.IOException
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket
import kotlin.coroutines.coroutineContext

/**
 * Development link to tools/fake_esp.py on the laptop. The emulator reaches
 * the host at 10.0.2.2: run `python3 tools/fake_esp.py --tcp 5555`.
 */
class TcpSource(
    private val host: String = DEFAULT_HOST,
    private val port: Int = DEFAULT_PORT,
) : DataSource {
    override val label = "TCP"

    @Volatile private var out: OutputStream? = null

    override fun lines(): Flow<ByteArray> = flow {
        var backoffMs = MIN_BACKOFF_MS
        while (coroutineContext.isActive) {
            val socket = Socket()
            try {
                coroutineScope {
                    // A blocking read() ignores cancellation. This child runs on
                    // another thread and closes the socket the moment the flow is
                    // cancelled, which makes read() throw and ends the loop.
                    val closer = launch(Dispatchers.IO) {
                        try {
                            awaitCancellation()
                        } finally {
                            socket.close()
                        }
                    }
                    socket.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
                    socket.tcpNoDelay = true
                    // hello comes every second, so a long silence means a dead connection.
                    socket.soTimeout = READ_TIMEOUT_MS
                    out = socket.getOutputStream()
                    backoffMs = MIN_BACKOFF_MS
                    val input = socket.getInputStream()
                    val splitter = LineSplitter()
                    val buf = ByteArray(4096)
                    val lines = ArrayList<ByteArray>()
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        lines.clear()
                        splitter.feed(buf, n) { lines.add(it) }
                        for (line in lines) emit(line)
                    }
                    closer.cancel()
                }
            } catch (e: IOException) {
                Log.d(TAG, "link to $host:$port: ${e.message}")
            } finally {
                out = null
                socket.close()
            }
            delay(backoffMs)
            backoffMs = (backoffMs * 2).coerceAtMost(MAX_BACKOFF_MS)
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun send(line: String) {
        val o = out ?: return
        withContext(Dispatchers.IO) {
            try {
                o.write((line.trimEnd('\n') + "\n").toByteArray(Charsets.UTF_8))
                o.flush()
            } catch (e: IOException) {
                Log.d(TAG, "send failed: ${e.message}")
            }
        }
    }

    companion object {
        const val DEFAULT_HOST = "10.0.2.2"
        const val DEFAULT_PORT = 5555
        private const val CONNECT_TIMEOUT_MS = 2000
        private const val READ_TIMEOUT_MS = 5000
        private const val MIN_BACKOFF_MS = 500L
        private const val MAX_BACKOFF_MS = 4000L
        private const val TAG = "TcpSource"
    }
}
