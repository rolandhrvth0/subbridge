package hu.rolandhrvth.subbridge.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

data class Palette(val bg: Color, val surface: Color, val surface2: Color, val line: Color, val text: Color,
                   val muted: Color, val accent: Color, val accentInk: Color, val ok: Color, val warn: Color, val dark: Boolean)

val DarkPalette = Palette(Color(0xFF0F1115), Color(0xFF181B21), Color(0xFF22262D), Color(0xFF2C313A), Color(0xFFECEEF2),
    Color(0xFF8D95A4), Color(0xFFF5B83D), Color(0xFF1A1405), Color(0xFF4CCF8A), Color(0xFFF5B83D), true)
val LightPalette = Palette(Color(0xFFF4F5F7), Color(0xFFFFFFFF), Color(0xFFEEF0F3), Color(0xFFE1E4E9), Color(0xFF16191E),
    Color(0xFF69717F), Color(0xFFC98A12), Color(0xFFFFFFFF), Color(0xFF1F9D5C), Color(0xFFB7791F), false)

val LocalPalette = staticCompositionLocalOf { DarkPalette }

/** Same speaker hue order as the desktop app and the web page. */
private val HUES = floatArrayOf(38f, 205f, 140f, 330f, 265f, 15f, 175f, 85f, 300f, 230f)
private val assigned = mutableMapOf<String, Float>()
fun speakerColor(name: String, dark: Boolean): Color {
    val k = name.lowercase()
    val h = assigned.getOrPut(k) { HUES.firstOrNull { it !in assigned.values } ?: HUES[assigned.size % HUES.size] }
    return Color.hsl(h, if (dark) 0.75f else 0.65f, if (dark) 0.66f else 0.36f)
}

@Composable
fun SubBridgeTheme(dark: Boolean, content: @Composable () -> Unit) {
    val p = if (dark) DarkPalette else LightPalette
    val scheme = if (dark) darkColorScheme(primary = p.accent, onPrimary = p.accentInk, background = p.bg, surface = p.surface,
        onBackground = p.text, onSurface = p.text, surfaceVariant = p.surface2, outline = p.line)
    else lightColorScheme(primary = p.accent, onPrimary = p.accentInk, background = p.bg, surface = p.surface,
        onBackground = p.text, onSurface = p.text, surfaceVariant = p.surface2, outline = p.line)
    androidx.compose.runtime.CompositionLocalProvider(LocalPalette provides p) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}
