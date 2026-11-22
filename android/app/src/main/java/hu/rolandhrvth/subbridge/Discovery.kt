package hu.rolandhrvth.subbridge

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.os.Handler
import android.os.Looper
import kotlinx.coroutines.flow.MutableStateFlow

/** Finds computers running SubBridge on the local network (mDNS service _subbridge._tcp). */
class Discovery(ctx: Context) {
    private val nsd = ctx.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val wifi = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val main = Handler(Looper.getMainLooper())
    private var lock: WifiManager.MulticastLock? = null
    private var listener: NsdManager.DiscoveryListener? = null
    private val resolving = ArrayDeque<NsdServiceInfo>()
    private var busy = false

    val servers = MutableStateFlow<List<Server>>(emptyList())

    fun start() {
        if (listener != null) return
        lock = wifi.createMulticastLock("subbridge").apply { setReferenceCounted(false); acquire() }
        val l = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) {}
            override fun onDiscoveryStopped(serviceType: String) {}
            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {}
            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {}
            override fun onServiceFound(info: NsdServiceInfo) = main.post { queue(info) }.let { }
            override fun onServiceLost(info: NsdServiceInfo) {
                main.post { servers.value = servers.value.filterNot { it.name == clean(info.serviceName) } }
            }
        }
        listener = l
        nsd.discoverServices("_subbridge._tcp", NsdManager.PROTOCOL_DNS_SD, l)
    }

    fun stop() {
        listener?.let { runCatching { nsd.stopServiceDiscovery(it) } }
        listener = null
        lock?.release()
        lock = null
    }

    private fun clean(n: String) = n.removePrefix("SubBridge on ").ifEmpty { n }

    // NsdManager resolves one service at a time
    private fun queue(info: NsdServiceInfo) {
        resolving.addLast(info)
        next()
    }

    @Suppress("DEPRECATION")
    private fun next() {
        if (busy) return
        val info = resolving.removeFirstOrNull() ?: return
        busy = true
        nsd.resolveService(info, object : NsdManager.ResolveListener {
            override fun onResolveFailed(si: NsdServiceInfo, errorCode: Int) {
                main.post { busy = false; next() }
            }

            override fun onServiceResolved(si: NsdServiceInfo) {
                val host = si.host?.hostAddress
                val https = si.attributes["https"]?.let { String(it) } == "1"
                main.post {
                    if (host != null && !host.contains(":")) {
                        val s = Server(host, si.port, https, clean(si.serviceName))
                        servers.value = (servers.value.filterNot { it.key == s.key } + s).sortedBy { it.name }
                    }
                    busy = false
                    next()
                }
            }
        })
    }
}
