package hu.rolandhrvth.subbridge

import android.app.Application
import android.content.Context
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch

data class Prefs(
    val size: Float = 28f, val original: Boolean = true, val tts: Boolean = false, val names: Boolean = false,
    val rate: Float = 1.05f, val keepOn: Boolean = true, val dark: Boolean = true,
)

class AppModel(app: Application) : AndroidViewModel(app) {
    private val sp = app.getSharedPreferences("sb.ui", Context.MODE_PRIVATE)
    val client = Client(app)
    val discovery = Discovery(app)
    private val speech = Speech(app)
    val prefs = MutableStateFlow(load())

    init {
        client.savedServer()?.let { s -> if (client.savedToken(s) != null) client.connect(s) }
        viewModelScope.launch {
            client.lastNew.collect { l ->
                val p = prefs.value
                if (l != null && p.tts) speech.speak(l.text, l.speaker, p.rate, p.names)
            }
        }
    }

    private fun load() = Prefs(
        sp.getFloat("size", 28f), sp.getBoolean("original", true), sp.getBoolean("tts", false),
        sp.getBoolean("names", false), sp.getFloat("rate", 1.05f), sp.getBoolean("keepOn", true),
        sp.getBoolean("dark", true))

    fun update(f: (Prefs) -> Prefs) {
        val p = f(prefs.value)
        prefs.value = p
        if (!p.tts) speech.stop()
        sp.edit().putFloat("size", p.size).putBoolean("original", p.original).putBoolean("tts", p.tts)
            .putBoolean("names", p.names).putFloat("rate", p.rate).putBoolean("keepOn", p.keepOn)
            .putBoolean("dark", p.dark).apply()
    }

    override fun onCleared() {
        client.disconnect()
        discovery.stop()
        speech.shutdown()
    }
}
