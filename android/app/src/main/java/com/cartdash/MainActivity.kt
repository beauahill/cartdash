package com.cartdash

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.compose.setContent
import androidx.compose.runtime.getValue
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.cartdash.data.SourceKind
import com.cartdash.ui.DashScreen

class MainActivity : ComponentActivity() {
    private val app get() = application as CartDashApp

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.getInsetsController(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
        // The dash is home: back does nothing.
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {}
        })
        applySourceExtra()

        setContent {
            val snap by app.link.snapshot.collectAsStateWithLifecycle()
            DashScreen(snap, onSourceTap = {
                // Phase 0 stand-in for the settings screen: tap cycles the source.
                val all = SourceKind.entries
                app.sourceKind = all[(app.sourceKind.ordinal + 1) % all.size]
            })
        }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        applySourceExtra()
    }

    /**
     * For development:
     * `adb shell am start -n com.cartdash/.MainActivity --es source TCP --ei tcp_port 5600`.
     */
    private fun applySourceExtra() {
        intent?.getIntExtra("tcp_port", 0)?.takeIf { it in 1..65535 }?.let { app.tcpPort = it }
        val name = intent?.getStringExtra("source") ?: return
        runCatching { SourceKind.valueOf(name.uppercase()) }.getOrNull()?.let { app.sourceKind = it }
    }
}
