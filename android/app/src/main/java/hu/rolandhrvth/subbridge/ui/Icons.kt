package hu.rolandhrvth.subbridge.ui

import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.dp

/** Line icons (24px grid, same set as the desktop app) – no extra icon library needed. */
private fun line(name: String, vararg paths: String): ImageVector {
    val b = ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f)
    for (d in paths) b.addPath(PathParser().parsePathString(d).toNodes(), stroke = SolidColor(androidx.compose.ui.graphics.Color.Black),
        strokeLineWidth = 1.9f, strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round)
    return b.build()
}

object Ic {
    val settings = line("settings", "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12", "M14 6a2 2 0 1 0 4 0a2 2 0 1 0 -4 0",
        "M8 12a2 2 0 1 0 4 0a2 2 0 1 0 -4 0", "M16 18a2 2 0 1 0 4 0a2 2 0 1 0 -4 0")
    val volume = line("volume", "M11 5 6 9H3v6h3l5 4V5Z", "M15.5 8.5a5 5 0 0 1 0 7", "M18.5 5.5a9 9 0 0 1 0 13")
    val mute = line("mute", "M11 5 6 9H3v6h3l5 4V5Z", "M22 9l-6 6M16 9l6 6")
    val qr = line("qr", "M3 3h7v7H3z", "M14 3h7v7h-7z", "M3 14h7v7H3z", "M14 14h3v3h-3zM20 14v.01M14 20h.01M20 20h.01M17 20v.01M20 17v.01")
    val monitor = line("monitor", "M4 3h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z", "M8 21h8M12 17v4")
    val edit = line("edit", "M12 20h9", "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z")
    val down = line("down", "M12 5v14M5 12l7 7 7-7")
    val close = line("close", "M18 6 6 18M6 6l12 12")
}
