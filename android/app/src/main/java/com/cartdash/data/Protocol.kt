package com.cartdash.data

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull
import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction

/** A message received from the ESP32. */
sealed interface Message {
    data class State(val state: CartState) : Message
    data class HelloMsg(val hello: Hello) : Message
    data class Log(val log: LogLine) : Message
    /** A JSON object with a `type` this app does not know. Callers ignore it. */
    data class Unknown(val type: String) : Message
}

/**
 * The receiver rules from docs/usb_protocol.md, ported from
 * tools/cartdash_proto.py. Values are type checked by hand instead of decoded
 * into a strict class: a wrong-typed required field drops the message, a
 * wrong-typed optional field counts as missing.
 */
object Protocol {
    const val PROTO_VERSION = 1L
    const val MAX_LINE_BYTES = 2048
    const val LINK_LOST_AFTER_MS = 1000L

    private val json = Json { isLenient = false }

    /** The message in one received line, or null if the line must be dropped. */
    fun parseLine(raw: ByteArray): Message? {
        var end = raw.size
        if (end > 0 && raw[end - 1] == '\n'.code.toByte()) end--
        if (end > 0 && raw[end - 1] == '\r'.code.toByte()) end--
        if (end == 0 || end > MAX_LINE_BYTES) return null
        val text = try {
            Charsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(raw, 0, end))
                .toString()
        } catch (e: CharacterCodingException) {
            return null
        }
        return parseText(text)
    }

    fun parseLine(raw: String): Message? = parseLine(raw.toByteArray(Charsets.UTF_8))

    private fun parseText(text: String): Message? {
        val obj = try {
            json.parseToJsonElement(text)
        } catch (e: Exception) {
            return null
        } as? JsonObject ?: return null
        val type = obj["type"].str() ?: return null
        return when (type) {
            "state" -> parseState(obj)
            "hello" -> parseHello(obj)
            "log" -> parseLog(obj)
            else -> Message.Unknown(type)
        }
    }

    private fun parseState(o: JsonObject): Message? {
        val seq = o["seq"].int() ?: return null
        val t = o["t"].int() ?: return null
        val stale = (o["stale"] as? JsonArray)?.mapNotNull { it.str() }?.toSet() ?: emptySet()

        fun num(name: String) = if (name in stale) null else o[name].num()
        fun bool(name: String) = if (name in stale) null else o[name].bool()
        fun str(name: String) = if (name in stale) null else o[name].str()
        fun nums(name: String) = if (name in stale) null else (o[name] as? JsonArray)?.let { a ->
            a.map { it.num() ?: return@let null }
        }
        fun strs(name: String) = if (name in stale) null else (o[name] as? JsonArray)?.let { a ->
            a.map { it.str() ?: return@let null }
        }

        return Message.State(
            CartState(
                seq = seq,
                t = t,
                speedMph = num("speed_mph"),
                gear = str("gear")?.takeIf { it == "D" || it == "N" || it == "R" },
                speedMode = str("speed_mode"),
                socPct = num("soc_pct"),
                packV = num("pack_v"),
                packA = num("pack_a"),
                powerKw = num("power_kw"),
                cellVMin = num("cell_v_min"),
                cellVMax = num("cell_v_max"),
                bmsTempF = nums("bms_temp_f"),
                ctrlTempF = num("ctrl_temp_f"),
                motorTempF = num("motor_temp_f"),
                motorRpm = num("motor_rpm"),
                turnLeft = bool("turn_left"),
                turnRight = bool("turn_right"),
                lowBeam = bool("low_beam"),
                highBeam = bool("high_beam"),
                brake = bool("brake"),
                parkBrake = bool("park_brake"),
                reverse = bool("reverse"),
                illum = bool("illum"),
                kellyFaults = strs("kelly_faults"),
                bmsFaults = strs("bms_faults"),
                stale = stale,
            )
        )
    }

    private fun parseHello(o: JsonObject): Message? {
        val proto = o["proto"].int() ?: return null
        val fw = o["fw"].str() ?: return null
        val uptime = o["uptime_s"].int() ?: return null
        return Message.HelloMsg(Hello(proto, fw, uptime, o["sim"].bool()))
    }

    private fun parseLog(o: JsonObject): Message? {
        val msg = o["msg"].str()
        val frame = o["frame"].str()
        if (msg == null && frame == null) return null
        return Message.Log(LogLine(o["lvl"].str(), o["tag"].str(), msg, frame, o["t"].int()))
    }

    // JSON type checks. A JSON string "5" is not a number and true is not an int.

    private fun JsonElement?.prim(): JsonPrimitive? =
        if (this is JsonPrimitive && this !is JsonNull) this else null

    private fun JsonElement?.str(): String? = prim()?.takeIf { it.isString }?.content

    private fun JsonElement?.bool(): Boolean? = prim()?.takeIf { !it.isString }?.booleanOrNull

    private fun JsonElement?.num(): Double? = prim()?.takeIf { !it.isString }?.let {
        if (it.booleanOrNull != null) null else it.doubleOrNull
    }

    /** Whole numbers only, like Python's int: 1.0 is not an int. */
    private fun JsonElement?.int(): Long? = prim()?.takeIf { !it.isString }?.longOrNull
}
