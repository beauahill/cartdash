package com.cartdash.ui.theme

import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/**
 * Two palettes, high contrast, no mid-gray text. Day is dark text on white,
 * which often reads better than a dark screen on a glossy panel in direct
 * sun; check both outside (plan, Phase 6). Night follows the `illum` signal.
 */
@Immutable
data class DashColors(
    val background: Color,
    val text: Color,
    val dim: Color,       // labels and inactive indicators
    val panel: Color,     // tile backgrounds
    val green: Color,
    val amber: Color,
    val red: Color,
    val blue: Color,
    val onBanner: Color,
)

val DayColors = DashColors(
    background = Color(0xFFFFFFFF),
    text = Color(0xFF000000),
    dim = Color(0xFF8A8A8A),
    panel = Color(0xFFEDEDED),
    green = Color(0xFF008A3A),
    amber = Color(0xFFE08A00),
    red = Color(0xFFD50000),
    blue = Color(0xFF0040E0),
    onBanner = Color(0xFFFFFFFF),
)

val NightColors = DashColors(
    background = Color(0xFF000000),
    text = Color(0xFFFFFFFF),
    dim = Color(0xFF5A5A5A),
    panel = Color(0xFF161616),
    green = Color(0xFF00E676),
    amber = Color(0xFFFFB300),
    red = Color(0xFFFF1744),
    blue = Color(0xFF448AFF),
    onBanner = Color(0xFF000000),
)

val LocalDashColors = staticCompositionLocalOf { NightColors }
