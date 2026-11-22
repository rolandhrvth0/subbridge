package hu.rolandhrvth.subbridge.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import hu.rolandhrvth.subbridge.AppModel
import hu.rolandhrvth.subbridge.Conn
import hu.rolandhrvth.subbridge.Problem
import hu.rolandhrvth.subbridge.R
import hu.rolandhrvth.subbridge.Server

@Composable
fun Logo(size: Int = 64) {
    val p = LocalPalette.current
    Box(Modifier.size(size.dp).background(p.surface2, RoundedCornerShape((size / 4).dp)), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size((size * 0.6).dp)) {
            val w = this.size.width
            drawArc(p.text, 200f, 140f, false, Offset(w * 0.18f, w * 0.12f), Size(w * 0.64f, w * 0.64f),
                style = Stroke(w * 0.075f, cap = StrokeCap.Round))
            drawRoundRect(p.accent, Offset(w * 0.1f, w * 0.55f), Size(w * 0.8f, w * 0.12f), CornerRadius(w * 0.06f))
            drawRoundRect(p.accent.copy(alpha = 0.6f), Offset(w * 0.22f, w * 0.75f), Size(w * 0.56f, w * 0.12f), CornerRadius(w * 0.06f))
        }
    }
}

@Composable
fun ConnectScreen(vm: AppModel) {
    val p = LocalPalette.current
    val found by vm.discovery.servers.collectAsStateWithLifecycle()
    val conn by vm.client.conn.collectAsStateWithLifecycle()
    val problem by vm.client.problem.collectAsStateWithLifecycle()
    var pinFor by remember { mutableStateOf<Server?>(null) }
    var manual by remember { mutableStateOf(false) }

    val scan = rememberLauncherForActivityResult(ScanContract()) { r ->
        r.contents?.let { Server.fromQr(it) }?.let { (s, tok) ->
            if (tok != null) vm.client.connect(s, token = tok) else pinFor = s
        }
    }

    Column(
        Modifier.fillMaxSize().background(p.bg).statusBarsPadding().navigationBarsPadding()
            .verticalScroll(rememberScrollState()).padding(horizontal = 22.dp, vertical = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(24.dp))
        Logo(72)
        Spacer(Modifier.height(16.dp))
        Text("SubBridge", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = p.text)
        Text(stringResource(R.string.tagline), color = p.muted, fontSize = 15.sp)
        Spacer(Modifier.height(30.dp))

        Column(Modifier.fillMaxWidth().background(p.surface, RoundedCornerShape(18.dp)).border(1.dp, p.line, RoundedCornerShape(18.dp)).padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(if (found.isEmpty()) R.string.searching else R.string.found), color = p.muted,
                    fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                if (found.isEmpty()) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = p.accent)
            }
            Spacer(Modifier.height(10.dp))
            if (found.isEmpty()) {
                Text(stringResource(R.string.none_found), color = p.muted, fontSize = 14.sp)
            }
            for (s in found) {
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 4.dp).background(p.surface2, RoundedCornerShape(12.dp))
                        .clickable {
                            if (vm.client.savedToken(s) != null) vm.client.connect(s) else pinFor = s
                        }.padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Ic.monitor, null, tint = p.accent, modifier = Modifier.size(22.dp))
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(s.name, color = p.text, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                        Text("${s.host}:${s.port}", color = p.muted, fontSize = 13.sp)
                    }
                    if (conn == Conn.Connecting && vm.client.server.value?.key == s.key)
                        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = p.accent)
                }
            }
        }

        Spacer(Modifier.height(16.dp))
        Button(onClick = { scan.launch(ScanOptions().setPrompt("").setBeepEnabled(false).setOrientationLocked(false)) },
            modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(14.dp),
            colors = ButtonDefaults.buttonColors(containerColor = p.accent, contentColor = p.accentInk)) {
            Icon(Ic.qr, null, Modifier.size(20.dp))
            Spacer(Modifier.width(10.dp))
            Text(stringResource(R.string.scan_qr), fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
        }
        Spacer(Modifier.height(10.dp))
        OutlinedButton(onClick = { manual = true }, modifier = Modifier.fillMaxWidth().height(50.dp), shape = RoundedCornerShape(14.dp)) {
            Icon(Ic.edit, null, Modifier.size(18.dp), tint = p.text)
            Spacer(Modifier.width(10.dp))
            Text(stringResource(R.string.manual), color = p.text)
        }

        val err = when (problem) {
            Problem.BadPin -> R.string.bad_pin
            Problem.Locked -> R.string.locked
            Problem.Unreachable -> R.string.cant_reach
            Problem.CertChanged -> R.string.cert_changed
            Problem.None -> null
        }
        if (err != null) {
            Spacer(Modifier.height(16.dp))
            Text(stringResource(err), color = p.warn, textAlign = TextAlign.Center, fontSize = 14.sp)
        }
        Spacer(Modifier.height(28.dp))
        Text(stringResource(R.string.privacy), color = p.muted, fontSize = 12.sp, textAlign = TextAlign.Center)
    }

    pinFor?.let { s -> PinDialog(s, onDismiss = { pinFor = null }) { pin -> pinFor = null; vm.client.connect(s, pin = pin) } }
    if (manual) AddressDialog(onDismiss = { manual = false }) { s, pin -> manual = false; vm.client.connect(s, pin = pin) }
}

@Composable
private fun PinDialog(s: Server, onDismiss: () -> Unit, onPin: (String) -> Unit) {
    var pin by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text(s.name) },
        text = {
            Column {
                Text(stringResource(R.string.pin_hint))
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(pin, { v -> pin = v.filter { it.isDigit() }.take(6) }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                    textStyle = androidx.compose.ui.text.TextStyle(fontSize = 26.sp, letterSpacing = 8.sp, textAlign = TextAlign.Center))
            }
        },
        confirmButton = { TextButton(enabled = pin.length == 6, onClick = { onPin(pin) }) { Text(stringResource(R.string.connect)) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } })
}

@Composable
private fun AddressDialog(onDismiss: () -> Unit, onGo: (Server, String) -> Unit) {
    var addr by remember { mutableStateOf("") }
    var pin by remember { mutableStateOf("") }
    val s = Server.fromAddress(addr, addr.startsWith("https"))
    AlertDialog(onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.manual)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(addr, { addr = it.trim() }, singleLine = true, placeholder = { Text(stringResource(R.string.address_hint)) },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
                OutlinedTextField(pin, { v -> pin = v.filter { it.isDigit() }.take(6) }, singleLine = true,
                    label = { Text(stringResource(R.string.pin)) },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword))
            }
        },
        confirmButton = { TextButton(enabled = s != null && pin.length == 6, onClick = { onGo(s!!, pin) }) { Text(stringResource(R.string.connect)) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } })
}
