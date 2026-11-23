package com.cartdash

import android.app.Application
import android.content.Context
import android.os.SystemClock
import com.cartdash.data.CartLink
import com.cartdash.data.SimSource
import com.cartdash.data.SourceKind
import com.cartdash.data.TcpSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/** Owns the cart link for now. Phase 1 moves it into LinkService. */
class CartDashApp : Application() {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val link: CartLink by lazy {
        CartLink(scope, SystemClock::elapsedRealtime) { kind ->
            when (kind) {
                SourceKind.SIM -> SimSource()
                SourceKind.TCP -> TcpSource(port = tcpPort)
            }
        }
    }

    /**
     * Port of tools/fake_esp.py on the laptop. 5555 by default, but an
     * emulator on the default console port also holds host port 5555 (see
     * docs/dev_setup.md), so it can be changed from adb.
     */
    var tcpPort: Int
        get() = prefs.getInt(KEY_TCP_PORT, TcpSource.DEFAULT_PORT)
        set(value) {
            prefs.edit().putInt(KEY_TCP_PORT, value).apply()
        }

    private val prefs by lazy { getSharedPreferences("cartdash", Context.MODE_PRIVATE) }

    var sourceKind: SourceKind
        get() = runCatching { SourceKind.valueOf(prefs.getString(KEY_SOURCE, null) ?: "") }.getOrDefault(SourceKind.SIM)
        set(value) {
            prefs.edit().putString(KEY_SOURCE, value.name).apply()
            link.start(value)
        }

    override fun onCreate() {
        super.onCreate()
        link.start(sourceKind)
    }

    companion object {
        private const val KEY_SOURCE = "source"
        private const val KEY_TCP_PORT = "tcp_port"
    }
}
