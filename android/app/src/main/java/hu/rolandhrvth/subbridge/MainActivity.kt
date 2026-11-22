package hu.rolandhrvth.subbridge

import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import hu.rolandhrvth.subbridge.ui.ConnectScreen
import hu.rolandhrvth.subbridge.ui.LiveScreen
import hu.rolandhrvth.subbridge.ui.SubBridgeTheme

class MainActivity : ComponentActivity() {
    private val vm: AppModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) handleLink(intent)
        setContent {
            val prefs by vm.prefs.collectAsStateWithLifecycle()
            LaunchedEffect(prefs.dark) {
                // light status-bar icons on the dark theme, dark icons on the light one
                val bar = if (prefs.dark) SystemBarStyle.dark(android.graphics.Color.TRANSPARENT)
                          else SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT)
                enableEdgeToEdge(statusBarStyle = bar, navigationBarStyle = bar)
            }
            val conn by vm.client.conn.collectAsStateWithLifecycle()
            val server by vm.client.server.collectAsStateWithLifecycle()
            val live = server != null && conn in setOf(Conn.Connected, Conn.Reconnecting)
            LaunchedEffect(live, prefs.keepOn) {
                if (live && prefs.keepOn) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
            SubBridgeTheme(dark = prefs.dark) {
                if (live) LiveScreen(vm) else ConnectScreen(vm)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleLink(intent)
    }

    private fun handleLink(intent: Intent?) {
        val u = intent?.data ?: return
        if (u.scheme != "subbridge" || u.host != "connect") return
        val host = u.getQueryParameter("host") ?: return
        val port = u.getQueryParameter("port")?.toIntOrNull() ?: 8765
        val s = Server(host, port, u.getQueryParameter("https") == "1")
        vm.client.connect(s, token = u.getQueryParameter("k"), pin = u.getQueryParameter("pin"))
    }

    override fun onStart() {
        super.onStart()
        vm.discovery.start()
    }

    override fun onStop() {
        vm.discovery.stop()
        super.onStop()
    }
}
