package com.cartdash.data

import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.roundToLong
import kotlin.math.sin
import kotlin.random.Random

/**
 * In-app simulator, so the dash runs with no ESP32 and no laptop. It builds
 * the same JSON lines the firmware sends and follows the same 60 s drive loop
 * as tools/fake_esp.py and firmware/src/sim.cpp. Every other loop is at night.
 * To exercise the banners and the "--" path, the Kelly drops out (fields go
 * stale) from 70 s to 77 s of every 90 s, and a BMS fault shows from 20 s to
 * 30 s of every third loop. The regen warning and link loss are covered by
 * fake_esp.py scenarios over TCP.
 */
class SimSource(private val seed: Int = 1) : DataSource {
    override val label = "SIM"

    override fun lines(): Flow<ByteArray> = flow {
        val model = Model(Random(seed))
        var tMs = 0L
        var lastHelloS = -1L
        while (true) {
            delay(PERIOD_MS)
            tMs += PERIOD_MS
            model.step(tMs, PERIOD_MS / 1000.0)
            if (tMs / 1000 != lastHelloS) {
                lastHelloS = tMs / 1000
                emit(hello(lastHelloS).toString().toByteArray())
            }
            emit(model.state(tMs).toString().toByteArray())
        }
    }

    override suspend fun send(line: String) {
        // The simulator ignores commands.
    }

    private fun hello(uptimeS: Long) = buildJsonObject {
        put("type", "hello")
        put("proto", Protocol.PROTO_VERSION)
        put("fw", "app-sim")
        put("uptime_s", uptimeS)
        put("sim", true)
    }

    internal class Model(private val rng: Random) {
        private var seq = 0L
        private var soc = 82.0
        private var ctrlTemp = 95.0
        private var motorTemp = 105.0
        private val values = LinkedHashMap<String, JsonPrimitive>()
        private val arrays = LinkedHashMap<String, List<Any>>()
        private val updated = HashMap<String, Long>()
        private var tMs = 0L

        fun step(tMs: Long, dt: Double) {
            this.tMs = tMs
            val t = tMs / 1000.0
            val tc = t % 60.0
            val night = (tMs / 60_000) % 2 == 1L
            val d = driveCycle(tc)
            val amps = d.amps + rng.nextDouble(-0.6, 0.6)
            soc = (soc + amps * dt / 3600.0 / PACK_AH * 100.0).coerceIn(0.0, 100.0)
            val packV = CELLS * cellOcv(soc) + amps * PACK_OHMS
            val load = abs(minOf(amps, 0.0))
            ctrlTemp += (95.0 + load * 0.12 - ctrlTemp) * dt / 120.0
            motorTemp += (100.0 + load * 0.25 - motorTemp) * dt / 300.0
            val motorRpm = d.mph * 63360.0 / 60.0 / (PI * WHEEL_DIA_IN) * GEAR_RATIO

            num("speed_mph", d.mph, 1)
            str("gear", d.gear)
            str("speed_mode", "high")
            bool("turn_left", d.left)
            bool("turn_right", d.right)
            bool("low_beam", night)
            bool("high_beam", false)
            bool("brake", d.brake)
            bool("park_brake", d.park)
            bool("reverse", d.reverse)
            bool("illum", night)

            val kellyOnline = t >= 0.3 && (tMs % 90_000) !in 70_000 until 77_000
            if (kellyOnline) {
                num("ctrl_temp_f", ctrlTemp, 0)
                num("motor_temp_f", motorTemp, 0)
                num("motor_rpm", motorRpm, 0)
                arr("kelly_faults", emptyList())
            }
            if (t >= 1.5) {
                val cell = packV / CELLS
                val spread = 0.004 + rng.nextDouble(0.0, 0.003)
                num("soc_pct", soc, 0)
                num("pack_v", packV, 2)
                num("pack_a", amps, 1)
                num("power_kw", packV * amps / 1000.0, 2)
                num("cell_v_min", cell - spread / 2, 3)
                num("cell_v_max", cell + spread / 2, 3)
                arr("bms_temp_f", listOf(78 + (load / 60).roundToInt(), 80 + (load / 50).roundToInt()))
                val fault = (tMs / 60_000) % 3 == 2L && tc >= 20 && tc < 30
                arr("bms_faults", if (fault) listOf("cell_ov") else emptyList())
            }
        }

        fun state(tMs: Long): JsonObject = buildJsonObject {
            put("type", "state")
            put("seq", seq++ and 0xFFFF_FFFFL)
            put("t", tMs and 0xFFFF_FFFFL)
            values.forEach { (k, v) -> put(k, v) }
            arrays.forEach { (k, list) ->
                putJsonArray(k) {
                    list.forEach { item -> if (item is String) add(item) else add((item as Number).toInt()) }
                }
            }
            putJsonArray("stale") {
                updated.filter { (_, ts) -> tMs - ts > STALE_AFTER_MS }.keys.sorted().forEach { add(it) }
            }
        }

        private fun num(name: String, v: Double, decimals: Int) {
            val p = if (decimals == 0) JsonPrimitive(v.roundToLong()) else {
                val scale = Math.pow(10.0, decimals.toDouble())
                JsonPrimitive((v * scale).roundToLong() / scale)
            }
            values[name] = p
            updated[name] = tMs
        }

        private fun bool(name: String, v: Boolean) {
            values[name] = JsonPrimitive(v)
            updated[name] = tMs
        }

        private fun str(name: String, v: String) {
            values[name] = JsonPrimitive(v)
            updated[name] = tMs
        }

        private fun arr(name: String, v: List<Any>) {
            arrays[name] = v
            updated[name] = tMs
        }
    }

    private class Drive(
        val mph: Double = 0.0,
        val amps: Double = -2.0,
        val gear: String = "D",
        val brake: Boolean = false,
        val park: Boolean = false,
        val left: Boolean = false,
        val right: Boolean = false,
        val reverse: Boolean = false,
    )

    companion object {
        private const val PERIOD_MS = 100L
        private const val STALE_AFTER_MS = 2000L
        private const val CELLS = 20.0
        private const val PACK_AH = 130.0
        private const val PACK_OHMS = 0.015
        private const val WHEEL_DIA_IN = 22.0
        private const val GEAR_RATIO = 12.0

        private val OCV = listOf(
            0.0 to 2.90, 5.0 to 3.10, 10.0 to 3.20, 20.0 to 3.25, 40.0 to 3.29,
            60.0 to 3.31, 80.0 to 3.33, 90.0 to 3.34, 100.0 to 3.40,
        )

        private fun cellOcv(soc: Double): Double {
            val s = soc.coerceIn(0.0, 100.0)
            for (i in 1 until OCV.size) {
                val (s0, v0) = OCV[i - 1]
                val (s1, v1) = OCV[i]
                if (s <= s1) return v0 + (v1 - v0) * (s - s0) / (s1 - s0)
            }
            return OCV.last().second
        }

        /** Driver inputs for the 60 s loop. tc is seconds into the loop. */
        private fun driveCycle(tc: Double): Drive = when {
            tc < 2 -> Drive(brake = true)
            tc < 12 -> (15.0 * (tc - 2) / 10).let { Drive(mph = it, amps = -60.0 - 6.0 * it) }
            tc < 30 -> (15.0 + 0.4 * sin(tc)).let { Drive(mph = it, amps = -(20.0 + 1.8 * it), right = tc >= 18 && tc < 23) }
            tc < 36 -> Drive(mph = 15.0 - 7.0 * (tc - 30) / 6, amps = 18.0)
            tc < 44 -> Drive(mph = 8.0, amps = -(20.0 + 1.8 * 8.0), left = tc >= 37 && tc < 42)
            tc < 50 -> Drive(mph = 8.0 * (50 - tc) / 6, amps = 10.0, brake = true)
            tc < 56 -> Drive(park = tc >= 52, brake = tc < 52)
            tc < 59 -> Drive(gear = "R", reverse = true, mph = 2.0, amps = -25.0)
            else -> Drive()
        }
    }
}
