package hu.rolandhrvth.subbridge

import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

data class Server(val host: String, val port: Int, val https: Boolean, val name: String = host) {
    val key get() = "$host:$port"
    val wsUrl get() = "${if (https) "wss" else "ws"}://$host:$port/ws"

    companion object {
        /** "http(s)://ip:port/?k=TOKEN" (the desktop QR code) → server + token */
        fun fromQr(text: String): Pair<Server, String?>? {
            val m = Regex("^(https?)://([^/:]+):(\\d+)/?(?:\\?k=([A-Za-z0-9_\\-]+))?").find(text.trim()) ?: return null
            val (proto, host, port, tok) = m.destructured
            return Server(host, port.toInt(), proto == "https") to tok.ifEmpty { null }
        }

        fun fromAddress(text: String, https: Boolean = false): Server? {
            fromQr(text)?.let { return it.first }
            val m = Regex("^([^:/\\s]+)(?::(\\d+))?$").find(text.trim()) ?: return null
            return Server(m.groupValues[1], m.groupValues[2].ifEmpty { "8765" }.toInt(), https)
        }
    }
}

data class Line(val id: Int, val speaker: String?, val text: String, val original: String,
                val zone: String?, val zoneName: String?, val note: String?)

data class PhoneItem(val kind: String, val mine: Boolean, val name: String, val text: String, val en: String)
data class PhoneState(val header: String, val items: List<PhoneItem>)

enum class Conn { Idle, Connecting, Connected, Reconnecting, Failed }
enum class Problem { None, BadPin, Locked, Unreachable, CertChanged }

/** WebSocket client for the desktop app. All state is exposed as StateFlows (UI thread safe). */
class Client(private val ctx: Context) {
    private val prefs = ctx.getSharedPreferences("sb", Context.MODE_PRIVATE)
    private val main = Handler(Looper.getMainLooper())

    val conn = MutableStateFlow(Conn.Idle)
    val problem = MutableStateFlow(Problem.None)
    val lines = MutableStateFlow<List<Line>>(emptyList())
    val visible = MutableStateFlow<Set<Int>>(emptySet())
    val phone = MutableStateFlow<PhoneState?>(null)
    val running = MutableStateFlow(true)
    val latency = MutableStateFlow(0)
    val lastNew = MutableStateFlow<Line?>(null)        // for read-aloud
    private val _server = MutableStateFlow<Server?>(null)
    val server: StateFlow<Server?> = _server

    private var ws: WebSocket? = null
    private var authed = false
    private var wanted = false
    private var retry = 0
    private var gen = 0

    // ------------------------------------------------------------------ saved pairing
    fun savedServer(): Server? {
        val host = prefs.getString("host", null) ?: return null
        return Server(host, prefs.getInt("port", 8765), prefs.getBoolean("https", false), prefs.getString("name", host) ?: host)
    }

    fun savedToken(s: Server): String? = prefs.getString("token:${s.key}", null)

    fun forget() {
        val s = _server.value ?: savedServer()
        disconnect()
        prefs.edit().apply {
            remove("host"); remove("port"); remove("https"); remove("name")
            if (s != null) { remove("token:${s.key}"); remove("fp:${s.key}") }
        }.apply()
    }

    // ------------------------------------------------------------------ TLS: trust on first use
    private fun fingerprint(c: X509Certificate) =
        MessageDigest.getInstance("SHA-256").digest(c.encoded).joinToString("") { "%02x".format(it) }

    private fun httpClient(s: Server): OkHttpClient {
        val b = OkHttpClient.Builder().pingInterval(10, TimeUnit.SECONDS).connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.SECONDS)
        if (s.https) {
            // The desktop app uses a self-signed certificate: remember its fingerprint the first time
            // (pairing with PIN/QR), refuse a different one later.
            val tm = object : X509TrustManager {
                override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
                override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                    val fp = fingerprint(chain[0])
                    val known = prefs.getString("fp:${s.key}", null)
                    if (known == null) prefs.edit().putString("fp:${s.key}", fp).apply()
                    else if (known != fp) {
                        problem.value = Problem.CertChanged
                        throw CertificateException("certificate changed")
                    }
                }
                override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
            }
            val ssl = SSLContext.getInstance("TLS").apply { init(null, arrayOf(tm), SecureRandom()) }
            b.sslSocketFactory(ssl.socketFactory, tm).hostnameVerifier { _, _ -> true }
        }
        return b.build()
    }

    // ------------------------------------------------------------------ connection
    fun connect(s: Server, token: String? = null, pin: String? = null) {
        disconnect()
        wanted = true
        retry = 0
        _server.value = s
        problem.value = Problem.None
        open(s, token ?: savedToken(s), pin)
    }

    private fun open(s: Server, token: String?, pin: String?) {
        val my = ++gen
        conn.value = if (retry == 0) Conn.Connecting else Conn.Reconnecting
        authed = false
        ws = httpClient(s).newWebSocket(Request.Builder().url(s.wsUrl).build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                val hello = JSONObject().put("type", "auth")
                if (token != null) hello.put("token", token)
                if (pin != null) hello.put("pin", pin)
                webSocket.send(hello.toString())
                webSocket.send(JSONObject().put("type", "hello").put("device", "${Build.MANUFACTURER} ${Build.MODEL}").toString())
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                if (my != gen) return
                val m = try { JSONObject(text) } catch (e: Exception) { return }
                main.post { handle(s, m) }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                if (my == gen) main.post { lost(s) }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                if (my == gen) main.post { lost(s) }
            }
        })
    }

    private fun lost(s: Server) {
        if (!wanted || problem.value in setOf(Problem.BadPin, Problem.Locked, Problem.CertChanged)) {
            if (problem.value != Problem.None) conn.value = Conn.Failed
            return
        }
        val token = savedToken(s)
        if (token == null && !authed) {          // never paired: report instead of retrying forever
            problem.value = Problem.Unreachable
            conn.value = Conn.Failed
            return
        }
        retry++
        conn.value = Conn.Reconnecting
        val delay = (500L * (1 shl minOf(retry, 4))).coerceAtMost(8000)
        main.postDelayed({ if (wanted) open(s, savedToken(s), null) }, delay)
    }

    fun disconnect() {
        wanted = false
        gen++
        ws?.close(1000, null)
        ws = null
        conn.value = Conn.Idle
        main.removeCallbacksAndMessages(null)
    }

    private fun ping() {
        if (conn.value != Conn.Connected) return
        ws?.send(JSONObject().put("type", "ping").put("t", System.currentTimeMillis()).toString())
        main.postDelayed({ ping() }, 4000)
    }

    // ------------------------------------------------------------------ protocol
    private fun lineOf(o: JSONObject) = Line(
        o.optInt("id"), o.optString("speaker").takeIf { !o.isNull("speaker") && it.isNotEmpty() },
        o.optString("text"), o.optString("original"),
        o.optString("zone").takeIf { !o.isNull("zone") && it.isNotEmpty() },
        o.optString("zone_name").takeIf { !o.isNull("zone_name") && it.isNotEmpty() },
        o.optString("note").takeIf { !o.isNull("note") && it.isNotEmpty() })

    private fun handle(s: Server, m: JSONObject) {
        when (m.optString("type")) {
            "auth" -> if (m.optBoolean("ok")) {
                authed = true
                retry = 0
                conn.value = Conn.Connected
                problem.value = Problem.None
                prefs.edit().putString("host", s.host).putInt("port", s.port).putBoolean("https", s.https)
                    .putString("name", s.name).apply {
                        m.optString("token").takeIf { it.isNotEmpty() }?.let { putString("token:${s.key}", it) }
                    }.apply()
                ping()
            } else {
                problem.value = if (m.optString("reason") == "locked") Problem.Locked else Problem.BadPin
                prefs.edit().remove("token:${s.key}").apply()
                wanted = false
                conn.value = Conn.Failed
            }
            "history" -> {
                if (!authed) { authed = true; conn.value = Conn.Connected; retry = 0; ping() }
                val arr = m.optJSONArray("items")
                lines.value = (0 until (arr?.length() ?: 0)).map { lineOf(arr!!.getJSONObject(it)) }
                visible.value = ids(m)
            }
            "line" -> {
                val l = lineOf(m)
                val cur = lines.value
                val i = cur.indexOfFirst { it.id == l.id }
                lines.value = (if (i >= 0) cur.toMutableList().also { it[i] = l } else cur + l).takeLast(120)
                if (i < 0) lastNew.value = l
            }
            "visible" -> visible.value = ids(m)
            "phone" -> {
                val arr = m.optJSONArray("items")
                phone.value = if (arr == null || arr.length() == 0) null else PhoneState(
                    m.optString("header"),
                    (0 until arr.length()).map {
                        val o = arr.getJSONObject(it)
                        PhoneItem(o.optString("kind"), o.optBoolean("mine"), o.optString("name"), o.optString("text"), o.optString("en"))
                    })
            }
            "status" -> running.value = m.optString("state") != "stopped"
            "pong" -> latency.value = ((System.currentTimeMillis() - m.optLong("t")) / 2).toInt()
        }
    }

    private fun ids(m: JSONObject): Set<Int> {
        val a = m.optJSONArray(if (m.has("ids")) "ids" else "visible") ?: return emptySet()
        return (0 until a.length()).map { a.getInt(it) }.toSet()
    }
}
