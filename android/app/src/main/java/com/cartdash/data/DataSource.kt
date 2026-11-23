package com.cartdash.data

import kotlinx.coroutines.flow.Flow

/**
 * Where cart data comes from: the ESP32 over USB (Phase 1), tools/fake_esp.py
 * over TCP, or the in-app simulator. Every source produces the same raw JSON
 * lines, so all of them go through the same parser and link timer.
 */
interface DataSource {
    /** Short name for the badge on the dash. */
    val label: String

    /**
     * Received lines, without the newline. Collecting connects; the flow keeps
     * reconnecting on its own until the collector is cancelled.
     */
    fun lines(): Flow<ByteArray>

    /** Send one line (a `cmd` message) to the ESP32. Dropped if not connected. */
    suspend fun send(line: String)
}

enum class SourceKind { SIM, TCP }
