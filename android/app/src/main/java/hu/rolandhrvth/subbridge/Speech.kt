package hu.rolandhrvth.subbridge

import android.content.Context
import android.speech.tts.TextToSpeech
import java.util.Locale

/** Read-aloud with the phone's own voices; every speaker gets a slightly different pitch. */
class Speech(ctx: Context) : TextToSpeech.OnInitListener {
    private val tts = TextToSpeech(ctx.applicationContext, this)
    private var ready = false
    var language: Locale = Locale("hu", "HU")

    override fun onInit(status: Int) {
        ready = status == TextToSpeech.SUCCESS
        if (ready) tts.language = language
    }

    fun speak(text: String, speaker: String?, rate: Float, withName: Boolean) {
        if (!ready || text.isBlank()) return
        tts.setSpeechRate(rate)
        val pitch = speaker?.let { floatArrayOf(1f, 0.82f, 1.18f, 0.9f, 1.1f, 0.75f, 1.25f)[(it.lowercase().hashCode() and 0x7fffffff) % 7] } ?: 1f
        tts.setPitch(pitch)
        val say = if (withName && speaker != null) "$speaker: $text" else text
        tts.speak(say, TextToSpeech.QUEUE_ADD, null, "sb${System.nanoTime()}")
    }

    fun stop() { if (ready) tts.stop() }
    fun shutdown() = tts.shutdown()
}
