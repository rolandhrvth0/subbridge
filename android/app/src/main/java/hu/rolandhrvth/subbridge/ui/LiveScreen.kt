package hu.rolandhrvth.subbridge.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import hu.rolandhrvth.subbridge.AppModel
import hu.rolandhrvth.subbridge.Conn
import hu.rolandhrvth.subbridge.Line
import hu.rolandhrvth.subbridge.PhoneState
import hu.rolandhrvth.subbridge.Prefs
import hu.rolandhrvth.subbridge.R
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LiveScreen(vm: AppModel) {
    val p = LocalPalette.current
    val prefs by vm.prefs.collectAsStateWithLifecycle()
    val lines by vm.client.lines.collectAsStateWithLifecycle()
    val visible by vm.client.visible.collectAsStateWithLifecycle()
    val phone by vm.client.phone.collectAsStateWithLifecycle()
    val conn by vm.client.conn.collectAsStateWithLifecycle()
    val latency by vm.client.latency.collectAsStateWithLifecycle()
    val running by vm.client.running.collectAsStateWithLifecycle()
    var sheet by remember { mutableStateOf(false) }
    val list = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val atEnd by remember { derivedStateOf { list.layoutInfo.visibleItemsInfo.lastOrNull()?.index?.let { it >= list.layoutInfo.totalItemsCount - 2 } ?: true } }

    LaunchedEffect(lines.size) { if (lines.isNotEmpty() && atEnd) list.animateScrollToItem(lines.size - 1) }

    Box(Modifier.fillMaxSize().background(p.bg)) {
        Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
            // top bar
            Row(Modifier.fillMaxWidth().padding(start = 18.dp, end = 6.dp, top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(8.dp).background(if (conn == Conn.Connected) p.ok else p.warn, CircleShape))
                Spacer(Modifier.size(8.dp))
                Text(
                    if (conn == Conn.Connected) "${stringResource(R.string.connected)} · $latency ms" else stringResource(R.string.reconnecting),
                    color = p.muted, fontSize = 13.sp, modifier = Modifier.weight(1f))
                IconButton(onClick = { vm.update { it.copy(tts = !it.tts) } }) {
                    Icon(if (prefs.tts) Ic.volume else Ic.mute, null, tint = if (prefs.tts) p.accent else p.muted)
                }
                IconButton(onClick = { sheet = true }) { Icon(Ic.settings, null, tint = p.muted) }
            }

            if (lines.isEmpty()) {
                Column(Modifier.weight(1f).fillMaxWidth().padding(32.dp), verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally) {
                    Logo(56)
                    Spacer(Modifier.size(16.dp))
                    Text(stringResource(if (running) R.string.waiting_sub else R.string.paused), color = p.text,
                        fontSize = 19.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center)
                    Spacer(Modifier.size(6.dp))
                    Text(stringResource(R.string.waiting_sub_hint), color = p.muted, fontSize = 14.sp, textAlign = TextAlign.Center)
                }
            } else {
                LazyColumn(Modifier.weight(1f).fillMaxWidth(), state = list,
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp, 10.dp, 16.dp, if (phone != null) 320.dp else 24.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp, Alignment.Bottom)) {
                    items(lines, key = { it.id }) { l ->
                        val idx = lines.indexOf(l)
                        Bubble(l, latest = idx == lines.size - 1, live = l.id in visible, prefs = prefs,
                            older = lines.size - 1 - idx)
                    }
                }
            }
        }

        if (!atEnd && lines.isNotEmpty() && phone == null) {
            TextButton(onClick = { scope.launch { list.animateScrollToItem(lines.size - 1) } },
                modifier = Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(bottom = 18.dp)
                    .background(p.accent, RoundedCornerShape(99.dp))) {
                Icon(Ic.down, null, tint = p.accentInk, modifier = Modifier.size(16.dp))
                Spacer(Modifier.size(6.dp))
                Text(stringResource(R.string.new_subtitle), color = p.accentInk, fontWeight = FontWeight.SemiBold)
            }
        }

        AnimatedVisibility(phone != null, Modifier.align(Alignment.BottomCenter),
            enter = slideInVertically { it } + fadeIn(), exit = slideOutVertically { it } + fadeOut()) {
            phone?.let { PhoneCard(it, prefs) }
        }
    }

    if (sheet) ModalBottomSheet(onDismissRequest = { sheet = false }, containerColor = p.surface) {
        SettingsSheet(vm, prefs) { sheet = false }
    }
}

@Composable
private fun Bubble(l: Line, latest: Boolean, live: Boolean, prefs: Prefs, older: Int) {
    val p = LocalPalette.current
    val c = when {
        l.zone != null -> p.accent
        l.speaker != null -> speakerColor(l.speaker, p.dark)
        else -> p.muted
    }
    val label = l.zoneName ?: l.zone?.let { stringResource(when (it) {
        "help" -> R.string.zone_help; "objective" -> R.string.zone_objective; "notice" -> R.string.zone_notice
        else -> R.string.zone_other }) } ?: l.speaker
    val shape = RoundedCornerShape(16.dp)
    var m = Modifier.fillMaxWidth().animateContentSize()
    m = when {
        live -> m.background(c.copy(alpha = 0.08f).compositeOver(p.surface), shape).border(1.dp, c.copy(alpha = 0.4f), shape)
        latest -> m.background(p.surface, shape)
        else -> m
    }
    Column(m.padding(horizontal = 14.dp, vertical = 10.dp).alpha(if (latest || live) 1f else (0.62f - older * 0.04f).coerceAtLeast(0.35f)),
        horizontalAlignment = Alignment.CenterHorizontally) {
        if (label != null) Text(if (l.zone != null) label.uppercase() else label, color = c,
            fontWeight = FontWeight.Bold, fontSize = if (l.zone != null) 11.sp else 13.sp, letterSpacing = if (l.zone != null) 1.sp else 0.sp)
        Text(l.text, color = p.text, textAlign = TextAlign.Center, lineHeight = (prefs.size * (if (latest) 1.22f else 0.78f)).sp,
            fontSize = (prefs.size * if (latest) 1f else 0.64f).sp, fontWeight = if (latest) FontWeight.SemiBold else FontWeight.Medium)
        if (prefs.original && l.original.isNotEmpty()) Text(l.original, color = p.muted, textAlign = TextAlign.Center,
            fontSize = (prefs.size * if (latest) 0.5f else 0.42f).sp, modifier = Modifier.padding(top = 3.dp))
    }
}

private fun Color.compositeOver(bg: Color) = Color(
    red * alpha + bg.red * (1 - alpha), green * alpha + bg.green * (1 - alpha), blue * alpha + bg.blue * (1 - alpha), 1f)

@Composable
private fun PhoneCard(ph: PhoneState, prefs: Prefs) {
    val p = LocalPalette.current
    val scroll = rememberScrollState()
    LaunchedEffect(ph) { scroll.scrollTo(scroll.maxValue) }
    Column(Modifier.navigationBarsPadding().padding(12.dp).fillMaxWidth().heightIn(max = 460.dp)
        .background(p.surface, RoundedCornerShape(22.dp)).border(1.dp, p.line, RoundedCornerShape(22.dp))) {
        Column(Modifier.padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 8.dp)) {
            Text(stringResource(R.string.in_game_phone).uppercase(), color = p.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
            if (ph.header.isNotEmpty()) Text(ph.header, color = p.text, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        }
        HorizontalDivider(color = p.line)
        Column(Modifier.verticalScroll(scroll).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            val blue = Color(0xFF2F6DF6)
            for (it in ph.items) {
                val reply = it.kind == "reply"
                Row(Modifier.fillMaxWidth(), horizontalArrangement = if (it.mine) Arrangement.End else Arrangement.Start) {
                    val shape = RoundedCornerShape(16.dp)
                    var m = Modifier.widthIn(max = 300.dp)
                    m = when {
                        reply -> m.border(2.dp, blue, shape)
                        it.mine -> m.background(blue, shape)
                        else -> m.background(p.surface2, shape)
                    }
                    Column(m.padding(horizontal = 12.dp, vertical = 8.dp)) {
                        if (it.name.isNotEmpty()) Text(it.name, fontSize = 12.sp, fontWeight = FontWeight.Bold, color = p.muted)
                        Text(it.text, fontSize = (prefs.size * 0.6f).sp, lineHeight = (prefs.size * 0.78f).sp,
                            color = if (reply) blue else if (it.mine) Color.White else p.text)
                        if (prefs.original) Text(it.en, fontSize = (prefs.size * 0.42f).sp,
                            color = (if (it.mine && !reply) Color.White else p.muted).copy(alpha = 0.75f))
                    }
                }
            }
        }
    }
}

@Composable
private fun SettingsSheet(vm: AppModel, prefs: Prefs, close: () -> Unit) {
    val p = LocalPalette.current
    Column(Modifier.fillMaxWidth().padding(horizontal = 22.dp).padding(bottom = 30.dp).navigationBarsPadding()) {
        Text(stringResource(R.string.settings), fontSize = 20.sp, fontWeight = FontWeight.Bold, color = p.text)
        Spacer(Modifier.size(12.dp))
        Text(stringResource(R.string.text_size), color = p.muted, fontSize = 13.sp)
        Slider(prefs.size, { v -> vm.update { it.copy(size = v) } }, valueRange = 18f..48f)
        Toggle(R.string.show_original, prefs.original) { v -> vm.update { it.copy(original = v) } }
        Toggle(R.string.read_aloud, prefs.tts) { v -> vm.update { it.copy(tts = v) } }
        if (prefs.tts) {
            Toggle(R.string.speak_names, prefs.names) { v -> vm.update { it.copy(names = v) } }
            Text(stringResource(R.string.speech_rate), color = p.muted, fontSize = 13.sp)
            Slider(prefs.rate, { v -> vm.update { it.copy(rate = v) } }, valueRange = 0.6f..1.8f)
        }
        Toggle(R.string.keep_on, prefs.keepOn) { v -> vm.update { it.copy(keepOn = v) } }
        Toggle(R.string.theme_dark, prefs.dark) { v -> vm.update { it.copy(dark = v) } }
        Spacer(Modifier.size(14.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(onClick = { close(); vm.client.disconnect() }) { Text(stringResource(R.string.disconnect), color = p.text) }
            OutlinedButton(onClick = { close(); vm.client.forget() }) { Text(stringResource(R.string.forget), color = p.text) }
        }
    }
}

@Composable
private fun Toggle(label: Int, on: Boolean, set: (Boolean) -> Unit) {
    val p = LocalPalette.current
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(stringResource(label), color = p.text, fontSize = 16.sp, modifier = Modifier.weight(1f))
        Switch(on, set)
    }
}
