package com.cartdash.data

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/** Everything the dash needs, in one value. */
data class LinkSnapshot(
    /** Latest state. Null before the first one and while the link is lost. */
    val state: CartState? = null,
    val hello: Hello? = null,
    /** False when no line arrived for more than [Protocol.LINK_LOST_AFTER_MS]. */
    val linkUp: Boolean = false,
    val source: SourceKind = SourceKind.SIM,
    val sourceLabel: String = "",
    /** Lines received since the source started, for debugging. */
    val lines: Long = 0,
) {
    /** True when the data is simulated, by the app or by the ESP32's simulator. */
    val sim: Boolean get() = source == SourceKind.SIM || hello?.sim == true
}

/**
 * Holds the active [DataSource], parses its lines, and decides link status.
 * Link status comes from a timer on received lines, not from the connection
 * state: any line (state, hello, or log) counts. In Phase 1 LinkService owns
 * this object; for now the Application does.
 */
class CartLink(
    private val scope: CoroutineScope,
    private val clock: () -> Long,
    private val sourceFactory: (SourceKind) -> DataSource,
) {
    private val _snapshot = MutableStateFlow(LinkSnapshot())
    val snapshot: StateFlow<LinkSnapshot> = _snapshot.asStateFlow()

    private var source: DataSource? = null
    private var readJob: Job? = null
    private var timerJob: Job? = null
    @Volatile private var lastLineAt = Long.MIN_VALUE

    fun start(kind: SourceKind) {
        readJob?.cancel()
        timerJob?.cancel()
        val src = sourceFactory(kind)
        source = src
        lastLineAt = Long.MIN_VALUE
        _snapshot.value = LinkSnapshot(source = kind, sourceLabel = src.label)

        readJob = scope.launch {
            src.lines().collect { raw ->
                lastLineAt = clock()
                val msg = Protocol.parseLine(raw)
                _snapshot.update { s ->
                    val n = s.copy(linkUp = true, lines = s.lines + 1)
                    when (msg) {
                        is Message.State -> n.copy(state = msg.state)
                        is Message.HelloMsg -> n.copy(hello = msg.hello)
                        else -> n
                    }
                }
            }
        }
        timerJob = scope.launch {
            while (isActive) {
                delay(TIMER_TICK_MS)
                val last = lastLineAt
                val up = last != Long.MIN_VALUE && clock() - last <= Protocol.LINK_LOST_AFTER_MS
                if (!up && _snapshot.value.linkUp) {
                    _snapshot.update { it.copy(linkUp = false, state = null) }
                }
            }
        }
    }

    suspend fun send(line: String) {
        source?.send(line)
    }

    fun stop() {
        readJob?.cancel()
        timerJob?.cancel()
    }

    companion object {
        const val TIMER_TICK_MS = 100L
    }
}
