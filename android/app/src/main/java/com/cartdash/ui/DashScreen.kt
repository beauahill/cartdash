package com.cartdash.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.PlatformTextStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import com.cartdash.data.CartState
import com.cartdash.data.LinkSnapshot
import com.cartdash.ui.theme.DashColors
import com.cartdash.ui.theme.DayColors
import com.cartdash.ui.theme.LocalDashColors
import com.cartdash.ui.theme.NightColors

/**
 * The drive dash. Landscape, no scrolling. Every size is a fraction of the
 * screen height (`u` is 1% of it), so the layout keeps its proportions at any
 * density; the head unit's real density is still a VERIFY item.
 */
@Composable
fun DashScreen(snap: LinkSnapshot, onSourceTap: () -> Unit) {
    val st = snap.state
    // Night follows the headlights. Keep the last theme while illum is unknown,
    // so a dropout at night does not flash the screen white.
    val lastNight = remember { booleanArrayOf(true) }
    st?.illum?.let { lastNight[0] = it }
    val night = lastNight[0]
    val colors = if (night) NightColors else DayColors
    val speedBand = remember { SpeedDeadBand() }
    val mph = speedBand.update(st?.speedMph)

    CompositionLocalProvider(LocalDashColors provides colors) {
        BoxWithConstraints(Modifier.fillMaxSize().background(colors.background)) {
            val u = maxHeight / 100
            Column(Modifier.fillMaxSize().padding(horizontal = u * 2, vertical = u * 1.5f)) {
                TopStrip(st, snap, u, Modifier.height(u * 17))
                Row(Modifier.weight(1f).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    SpeedPanel(mph, st, u, Modifier.weight(1.15f).fillMaxHeight())
                    Spacer(Modifier.width(u * 2))
                    BatteryPanel(st, u, Modifier.weight(1f).fillMaxHeight())
                }
                TileRow(st, u, Modifier.height(u * 17).fillMaxWidth())
                StatusLine(snap, u, onSourceTap, Modifier.height(u * 5).fillMaxWidth())
            }
        }
    }
}

@Composable
private fun sp(u: Dp, n: Float): TextUnit = with(LocalDensity.current) { (u * n).toSp() }

@Composable
private fun Num(text: String, u: Dp, size: Float, color: Color, modifier: Modifier = Modifier, align: TextAlign = TextAlign.Center) {
    Text(
        text,
        modifier = modifier,
        maxLines = 1,
        softWrap = false,
        style = TextStyle(
            fontSize = sp(u, size),
            lineHeight = sp(u, size),
            fontWeight = FontWeight.Black,
            fontFeatureSettings = "tnum",  // tabular digits: numbers do not jitter sideways
            color = color,
            textAlign = align,
            // Trim the font's extra line spacing so a big number takes only its own height.
            platformStyle = PlatformTextStyle(includeFontPadding = false),
            lineHeightStyle = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.Both),
        ),
    )
}

@Composable
private fun Label(text: String, u: Dp, size: Float = 4f, color: Color = LocalDashColors.current.dim, modifier: Modifier = Modifier) {
    Text(
        text,
        modifier = modifier,
        maxLines = 1,
        style = TextStyle(fontSize = sp(u, size), fontWeight = FontWeight.Bold, color = color, letterSpacing = sp(u, 0.2f)),
    )
}

// Top: blinker arrows at the corners, warning banners between them.

@Composable
private fun TopStrip(st: CartState?, snap: LinkSnapshot, u: Dp, modifier: Modifier) {
    val c = LocalDashColors.current
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Arrow(left = true, on = st?.turnLeft == true, u = u, modifier = Modifier.width(u * 22).fillMaxHeight())
        Column(
            Modifier.weight(1f).fillMaxHeight().padding(horizontal = u * 2),
            verticalArrangement = Arrangement.spacedBy(u * 1, Alignment.CenterVertically),
        ) {
            val banners = banners(st, snap, c)
            banners.take(2).forEach { (text, color) -> Banner(text, color, u, Modifier.weight(1f, fill = false)) }
        }
        Arrow(left = false, on = st?.turnRight == true, u = u, modifier = Modifier.width(u * 22).fillMaxHeight())
    }
}

private fun banners(st: CartState?, snap: LinkSnapshot, c: DashColors): List<Pair<String, Color>> {
    val out = ArrayList<Pair<String, Color>>()
    if (!snap.linkUp) out += "LINK LOST" to c.red
    if (st == null) return out
    if (st.regenWarning) out += "REGEN INTO FULL PACK" to c.amber
    st.bmsFaults?.takeIf { it.isNotEmpty() }?.let { out += "BMS FAULT ${it.joinToString(" ").uppercase()}" to c.red }
    st.kellyFaults?.takeIf { it.isNotEmpty() }?.let { out += "CONTROLLER FAULT ${it.joinToString(" ").uppercase()}" to c.red }
    return out
}

@Composable
private fun Banner(text: String, color: Color, u: Dp, modifier: Modifier) {
    Box(
        modifier.fillMaxWidth().clip(RoundedCornerShape(u * 1.5f)).background(color).padding(vertical = u * 0.8f),
        contentAlignment = Alignment.Center,
    ) {
        Num(text, u, 5.5f, LocalDashColors.current.onBanner)
    }
}

@Composable
private fun Arrow(left: Boolean, on: Boolean, u: Dp, modifier: Modifier) {
    val c = LocalDashColors.current
    Canvas(modifier.padding(u * 1)) {
        val w = size.width
        val h = size.height
        val p = Path().apply {
            // Arrow pointing right, mirrored for left.
            fun x(v: Float) = if (left) w - v else v
            moveTo(x(0f), h * 0.32f)
            lineTo(x(w * 0.55f), h * 0.32f)
            lineTo(x(w * 0.55f), 0f)
            lineTo(x(w), h * 0.5f)
            lineTo(x(w * 0.55f), h)
            lineTo(x(w * 0.55f), h * 0.68f)
            lineTo(x(0f), h * 0.68f)
            close()
        }
        if (on) drawPath(p, c.green) else drawPath(p, c.dim, style = Stroke(width = u.toPx() * 0.6f))
    }
}

// Middle left: speed, gear, speed mode.

@Composable
private fun SpeedPanel(mph: Int?, st: CartState?, u: Dp, modifier: Modifier) {
    val c = LocalDashColors.current
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        // Fits the 58u middle row: 38 for the number, 12 for the MPH, gear, and mode line.
        Num(mph?.toString() ?: DASH, u, 38f, if (mph == null) c.dim else c.text)
        Spacer(Modifier.height(u * 2))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Label("MPH", u, 5f)
            Spacer(Modifier.width(u * 4))
            val gear = st?.gear
            val gearColor = when (gear) {
                "R" -> c.amber
                null -> c.dim
                else -> c.text
            }
            Num(gear ?: DASH, u, 12f, gearColor)
            Spacer(Modifier.width(u * 4))
            Label(st?.speedMode?.uppercase() ?: DASH, u, 5f, if (st?.speedMode == null) c.dim else c.text)
        }
    }
}

// Middle right: state of charge and pack readings.

@Composable
private fun BatteryPanel(st: CartState?, u: Dp, modifier: Modifier) {
    val c = LocalDashColors.current
    val soc = st?.socPct
    val socColor = when {
        soc == null -> c.dim
        soc < 15 -> c.red
        soc < 30 -> c.amber
        else -> c.text
    }
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Row(verticalAlignment = Alignment.Bottom) {
            Num(fmt(soc), u, 30f, socColor)
            Num("%", u, 12f, if (soc == null) c.dim else c.text, Modifier.padding(bottom = u * 2.5f))
        }
        SocBar(soc, socColor, u, Modifier.fillMaxWidth(0.85f).height(u * 4.5f))
        Spacer(Modifier.height(u * 2.5f))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
            Reading(fmt(st?.packV, 1), "VOLTS", u)
            Reading(fmt(st?.packA, 0), "AMPS", u)
            Reading(fmt(st?.powerKw, 1), "KW", u, color = st?.powerKw?.let { if (it > 0) c.green else c.text })
        }
    }
}

@Composable
private fun SocBar(soc: Double?, color: Color, u: Dp, modifier: Modifier) {
    val c = LocalDashColors.current
    Canvas(modifier) {
        val r = androidx.compose.ui.geometry.CornerRadius(u.toPx(), u.toPx())
        drawRoundRect(c.panel, cornerRadius = r)
        if (soc != null) {
            val f = (soc / 100.0).coerceIn(0.0, 1.0).toFloat()
            drawRoundRect(color, size = size.copy(width = size.width * f), cornerRadius = r)
        }
        drawRoundRect(c.dim, cornerRadius = r, style = Stroke(width = u.toPx() * 0.4f), topLeft = Offset.Zero)
    }
}

@Composable
private fun Reading(value: String, label: String, u: Dp, color: Color? = null) {
    val c = LocalDashColors.current
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Num(value, u, 9f, if (value == DASH) c.dim else (color ?: c.text))
        Label(label, u, 3.6f)
    }
}

// Bottom: temperatures, cells, lights and brakes.

@Composable
private fun TileRow(st: CartState?, u: Dp, modifier: Modifier) {
    val c = LocalDashColors.current
    Row(modifier.padding(vertical = u * 1), horizontalArrangement = Arrangement.spacedBy(u * 1.5f)) {
        Tile("CTRL °F", fmt(st?.ctrlTempF), u)
        Tile("MOTOR °F", fmt(st?.motorTempF), u)
        Tile("BMS °F", st?.bmsTempF?.takeIf { it.isNotEmpty() }?.let { fmt(it.max()) } ?: DASH, u)
        // Lowest cell only: a tile is about 21u wide at 2000x1200, too narrow for a range.
        Tile("CELL LOW V", fmt(st?.cellVMin, 2), u)
        Indicator("LOW", st?.lowBeam, c.green, u)
        Indicator("HIGH", st?.highBeam, c.blue, u)
        Indicator("BRAKE", st?.brake, c.red, u)
        Indicator("PARK", st?.parkBrake, c.red, u)
    }
}

@Composable
private fun RowScope.Tile(label: String, value: String, u: Dp, size: Float = 8f) {
    val c = LocalDashColors.current
    Column(
        Modifier.weight(1f).fillMaxHeight().clip(RoundedCornerShape(u * 1.5f)).background(c.panel),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Num(value, u, size, if (value == DASH) c.dim else c.text)
        Label(label, u, 3.2f)
    }
}

/** On: filled with its color. Off: outlined. Unknown: "--". */
@Composable
private fun RowScope.Indicator(label: String, on: Boolean?, color: Color, u: Dp) {
    val c = LocalDashColors.current
    val bg = if (on == true) color else c.panel
    Box(
        Modifier.weight(0.8f).fillMaxHeight().clip(RoundedCornerShape(u * 1.5f)).background(bg),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Num(label, u, 4.5f, if (on == true) c.onBanner else c.dim)
            if (on == null) Num(DASH, u, 4.5f, c.dim)
        }
    }
}

@Composable
private fun StatusLine(snap: LinkSnapshot, u: Dp, onSourceTap: () -> Unit, modifier: Modifier) {
    val c = LocalDashColors.current
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        if (snap.sim) {
            Box(Modifier.clip(RoundedCornerShape(u * 0.8f)).background(c.amber).padding(horizontal = u * 1.2f)) {
                Num("SIM", u, 3.6f, c.onBanner)
            }
            Spacer(Modifier.width(u * 1.5f))
        }
        Label(
            "SOURCE ${snap.sourceLabel}",
            u, 3.2f, c.dim,
            Modifier.clickable(onClick = onSourceTap).padding(horizontal = u * 1),
        )
        Spacer(Modifier.weight(1f))
        Label(snap.hello?.let { "FW ${it.fw}  UP ${it.uptimeS}s" } ?: "", u, 3.2f)
    }
}
