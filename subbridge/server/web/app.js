"use strict";
(() => {
  const $ = s => document.querySelector(s);
  const root = document.documentElement;

  // ------------------------------------------------------------------ i18n
  const T = {
    hu: {
      pair_title: "Csatlakozás", pair_text: "Írd be a számítógépen látható 6 jegyű PIN-kódot.", pair_btn: "Csatlakozás",
      bad_pin: "Hibás PIN-kód. Nézd meg újra a számítógépen.", locked: "Túl sok próbálkozás. Várj egy percet.",
      waiting: "Várakozás feliratra…", connected: "Csatlakozva", connecting: "Csatlakozás…", offline: "Nincs kapcsolat – újrapróbálom…",
      settings: "Beállítások", s_display: "Megjelenítés", s_size: "Betűméret", s_font: "Betűtípus", f_system: "Rendszer",
      s_theme: "Háttér", t_dark: "Sötét", t_black: "Fekete (OLED)", t_light: "Világos", s_color: "Szövegszín",
      c_default: "Alap", c_yellow: "Sárga", c_white: "Fehér", c_green: "Zöld", s_align: "Igazítás", a_center: "Középre", a_left: "Balra",
      s_original: "Eredeti szöveg mutatása", s_history: "Előzmények mutatása", s_lines: "Korábbi sorok száma",
      s_autoclear: "Elhalványítás csend után", ac_off: "Ki", ac_never: "Soha",
      s_speakname: "Beszélő nevének felolvasása", s_pitch: "Beszélőnként más hangmagasság",
      s_tts: "Felolvasás", s_tts_on: "Felolvasás bekapcsolva", s_voice: "Hang", s_rate: "Sebesség", s_volume: "Hangerő",
      s_interrupt: "Új felirat megszakítja a régit", s_device: "Eszköz", s_wake: "Képernyő ébren tartása", s_lang: "Nyelv",
      install_hint: "Tipp: a böngésző „Hozzáadás a kezdőképernyőhöz” menüjével alkalmazásként is elindíthatod.",
      forget: "Kapcsolat elfelejtése", default_voice: "Alapértelmezett",
      wake_unsupported: "Ezen a kapcsolaton a böngésző nem engedi ébren tartani a képernyőt. Állítsd a telefon automatikus zárolását „Soha”-ra (iPhone: Beállítások › Kijelző és fényerő › Automatikus zárolás), vagy kapcsold be a HTTPS-t a számítógépes alkalmazásban.",
      no_voice: "Ezen az eszközön nincs telepítve hang ehhez a nyelvhez.",
      st_stopped: "A fordítás áll – indítsd el a számítógépen.", phone_tag: "Telefon a játékban", zone_help: "Súgó", zone_objective: "Feladat", zone_notice: "Értesítés", zone_other: "Szöveg", jump: "Új felirat", st_waiting: "A számítógép nem lát képet.",
    },
    en: {
      pair_title: "Connect", pair_text: "Enter the 6-digit PIN shown on your computer.", pair_btn: "Connect",
      bad_pin: "Wrong PIN. Check the computer again.", locked: "Too many attempts. Wait a minute.",
      waiting: "Waiting for subtitles…", connected: "Connected", connecting: "Connecting…", offline: "Disconnected – retrying…",
      settings: "Settings", s_display: "Display", s_size: "Text size", s_font: "Font", f_system: "System",
      s_theme: "Background", t_dark: "Dark", t_black: "Black (OLED)", t_light: "Light", s_color: "Text colour",
      c_default: "Default", c_yellow: "Yellow", c_white: "White", c_green: "Green", s_align: "Alignment", a_center: "Centre", a_left: "Left",
      s_original: "Show original text", s_history: "Show history", s_lines: "Previous lines",
      s_autoclear: "Dim after silence", ac_off: "Off", ac_never: "Never",
      s_speakname: "Read the speaker's name", s_pitch: "Different pitch per speaker",
      s_tts: "Read aloud", s_tts_on: "Read subtitles aloud", s_voice: "Voice", s_rate: "Speed", s_volume: "Volume",
      s_interrupt: "New subtitle interrupts the old one", s_device: "Device", s_wake: "Keep screen awake", s_lang: "Language",
      install_hint: "Tip: use your browser's “Add to Home Screen” to launch it like an app.",
      forget: "Forget this connection", default_voice: "Default",
      wake_unsupported: "On this connection the browser cannot keep the screen awake. Set your phone's auto-lock to “Never” (iPhone: Settings › Display & Brightness › Auto-Lock), or enable HTTPS in the desktop app.",
      no_voice: "No voice for this language is installed on this device.",
      st_stopped: "Translation is paused – start it on the computer.", phone_tag: "In-game phone", zone_help: "Help", zone_objective: "Objective", zone_notice: "Notification", zone_other: "Text", jump: "New subtitle", st_waiting: "The computer can't see the game image.",
    },
  };

  // ------------------------------------------------------------------ settings
  const DEFAULTS = { size: 30, font: "inter", theme: "dark", color: "default", align: "center", original: true, history: true,
    lines: 4, autoclear: 0, tts: false, voice: "", rate: 1.05, volume: 1, interrupt: true, speakName: false, pitch: true, wake: true,
    lang: (navigator.language || "hu").toLowerCase().startsWith("hu") ? "hu" : "en" };
  const load = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
  const S = Object.assign({}, DEFAULTS, load("sb.settings", {}));
  const save = () => localStorage.setItem("sb.settings", JSON.stringify(S));
  const t = k => (T[S.lang] || T.hu)[k] || T.en[k] || k;

  function applyI18n() {
    root.lang = S.lang;
    document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
  }

  function apply() {
    root.dataset.theme = S.theme; root.dataset.font = S.font; root.dataset.color = S.color;
    root.style.setProperty("--size", S.size + "px");
    root.style.setProperty("--align", S.align);
    document.body.classList.toggle("no-original", !S.original);
    document.body.classList.toggle("no-history", !S.history);
    $('meta[name="theme-color"]').content = getComputedStyle(root).getPropertyValue("--bg").trim() || "#0f1115";
    $("#btn-tts").classList.toggle("on", S.tts);
    $("#btn-tts use").setAttribute("href", S.tts ? "#i-volume" : "#i-mute");
    if (typeof layout === "function") layout();
  }

  const bind = (id, key, type = "value", fmt) => {
    const el = $(id), out = $(id + "-v");
    const show = () => { if (out) out.textContent = fmt ? fmt(S[key]) : S[key]; };
    if (type === "checked") el.checked = !!S[key]; else el.value = S[key];
    show();
    el.addEventListener("input", () => {
      let v = type === "checked" ? el.checked : el.value;
      if (el.type === "range" || key === "autoclear") v = Number(v);
      S[key] = v; save(); show(); apply(); onSetting(key);
    });
  };

  function onSetting(key) {
    if (key === "lang") { applyI18n(); fillVoices(); setConn(connState); }
    if (key === "wake") updateWake();
    if (key === "tts" && S.tts) unlockSpeech();
    if (key === "tts" && !S.tts) speechSynthesis?.cancel();
    if (key === "autoclear") armClear();
  }

  // ------------------------------------------------------------------ auth
  const params = new URLSearchParams(location.search);
  if (params.get("k")) {
    localStorage.setItem("sb.token", params.get("k"));
    history.replaceState(null, "", location.pathname);
  }
  let token = localStorage.getItem("sb.token") || "";
  let pendingPin = "";

  $("#pin-form").addEventListener("submit", e => {
    e.preventDefault();
    const v = $("#pin").value.replace(/\D/g, "");
    if (v.length !== 6) { shake(); return; }
    pendingPin = v; $("#pair-error").textContent = ""; connect();
  });
  $("#pin").addEventListener("input", e => {
    e.target.value = e.target.value.replace(/\D/g, "").slice(0, 6);
    if (e.target.value.length === 6) $("#pin-form").requestSubmit();
  });
  function shake() { const c = $(".pair-card"); c.classList.remove("shake"); void c.offsetWidth; c.classList.add("shake"); }
  function showPair(msg) {
    $("#app").hidden = true; $("#pair").hidden = false;
    $("#pair-error").textContent = msg || "";
    if (msg) { shake(); $("#pin").value = ""; }
    $("#pin").focus();
  }
  function showApp() { $("#pair").hidden = true; $("#app").hidden = false; }

  // ------------------------------------------------------------------ connection
  let ws = null, retry = 0, connState = "connecting", pingTimer = null, lastRtt = null, authFailed = false;
  function setConn(state) {
    connState = state;
    const c = $("#conn");
    c.className = "conn " + ({ ok: "ok", connecting: "warn", offline: "bad" }[state] || "");
    $("#conn-text").textContent = t(state === "ok" ? "connected" : state) + (state === "ok" && lastRtt != null ? ` · ${lastRtt} ms` : "");
  }

  function connect() {
    if (ws) { try { ws.close(); } catch {} }
    setConn("connecting");
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);
    ws.onopen = () => {
      ws.send(JSON.stringify(pendingPin ? { pin: pendingPin } : { token }));
    };
    ws.onmessage = ev => {
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      handle(m);
    };
    ws.onclose = () => {
      clearInterval(pingTimer);
      if (authFailed) return;
      setConn("offline");
      const delay = Math.min(8000, 500 * 2 ** retry++);
      setTimeout(connect, delay);
    };
  }

  function handle(m) {
    switch (m.type) {
      case "auth":
        if (!m.ok) {
          authFailed = true; localStorage.removeItem("sb.token"); token = ""; pendingPin = "";
          showPair(t(m.reason === "locked" ? "locked" : "bad_pin"));
          setTimeout(() => { authFailed = false; }, 100);
          return;
        }
        retry = 0; token = m.token; pendingPin = ""; localStorage.setItem("sb.token", token);
        ws.send(JSON.stringify({ type: "hello", device: deviceName() }));
        showApp(); setConn("ok"); updateWake();
        clearInterval(pingTimer);
        pingTimer = setInterval(() => ws.readyState === 1 && ws.send(JSON.stringify({ type: "ping", t: performance.now() })), 5000);
        break;
      case "pong": lastRtt = Math.round(performance.now() - m.t); setConn("ok"); break;
      case "history": onHistory(m); break;
      case "line": onLine(m); break;
      case "visible": onVisible(m.ids || []); break;
      case "phone": onPhone(m); break;
      case "status": showStatus(m); break;
    }
  }

  function deviceName() {
    const ua = navigator.userAgent;
    if (/iPhone/.test(ua)) return "iPhone"; if (/iPad/.test(ua)) return "iPad";
    const a = ua.match(/Android[^;]*;\s*([^;)]+)/); if (a) return a[1].trim();
    return "Browser";
  }

  // ------------------------------------------------------------------ rendering (conversation)
  let targetLang = "hu";
  const entries = new Map();          // id -> message
  let visible = new Set(), clearTimer = null, stick = true;
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const NOTE = { hu: { Spanish: "spanyolul", French: "franciául", German: "németül", Russian: "oroszul", Italian: "olaszul",
    Portuguese: "portugálul", Chinese: "kínaiul", Japanese: "japánul", Korean: "koreaiul", Arabic: "arabul" } };
  const noteText = n => n ? ((NOTE[S.lang] || {})[n] || (S.lang === "hu" ? n : "in " + n)) : "";
  // every speaker keeps one clearly different colour (assigned in order of appearance, remembered)
  const HUES = [38, 205, 140, 330, 265, 15, 175, 85, 300, 230];
  const speakerHue = load("sb.speakers", {});
  function hue(name) {
    const k = (name || "").toLowerCase();
    if (!(k in speakerHue)) {
      const used = Object.values(speakerHue);
      speakerHue[k] = HUES.find(h => !used.includes(h)) ?? HUES[used.length % HUES.length];
      try { localStorage.setItem("sb.speakers", JSON.stringify(speakerHue)); } catch {}
    }
    return speakerHue[k];
  }
  function fill(li, m) {
    const who = m.zone ? `<span class="zone">${esc(m.zone_name || t("zone_" + m.zone))}</span>`
      : m.speaker ? `<span class="who">${esc(m.speaker)}</span>` : "";
    const note = m.note ? `<span class="note">${esc(noteText(m.note))}</span>` : "";
    li.innerHTML = (who || note ? `<div class="head">${who}${note}</div>` : "") +
      `<div class="t">${esc(m.text)}</div><div class="o">${esc(m.original)}</div>`;
    li.style.setProperty("--h", m.speaker ? hue(m.speaker) : 220);
    li.classList.toggle("nospeaker", !m.speaker);
  }
  const log = () => $("#log");
  const stage = () => $("#stage");
  function atBottom() { const st = stage(); return st.scrollHeight - st.scrollTop - st.clientHeight < 60; }
  function scrollDown(force) {
    const st = stage();
    if (force || stick) st.scrollTo({ top: st.scrollHeight, behavior: force ? "auto" : "smooth" });
  }

  function onLine(m, silent) {
    const prev = entries.get(m.id);
    entries.set(m.id, m);
    let li = log().querySelector(`li[data-id="${m.id}"]`);
    if (li) fill(li, m);
    else { li = document.createElement("li"); li.className = "msg"; li.dataset.id = m.id; fill(li, m); log().appendChild(li); }
    if (m.lang) targetLang = m.lang;
    document.body.classList.add("has-content");
    layout();
    if (!stick && !silent) $("#jump").hidden = false;
    scrollDown(silent);
    armClear();
    if (!silent) {
      if (!prev) speak(m.text, false, m.speaker);
      else if ((m.original || "").length > (prev.original || "").length + 12) {
        // a merged / continued sentence: read only what was added when possible
        const old = prev.text || "";
        speak(m.text.startsWith(old) ? m.text.slice(old.length).trim() || m.text : m.text, true, m.speaker);
      }
    }
  }

  function onHistory(m) {
    log().innerHTML = ""; entries.clear();
    (m.items || []).forEach(x => onLine(x, true));
    onVisible(m.visible || []);
    scrollDown(true);
  }

  function onVisible(ids) {
    visible = new Set(ids);
    log().querySelectorAll("li.msg").forEach(li => li.classList.toggle("live", visible.has(Number(li.dataset.id))));
    layout();
  }

  // only what the reader needs: the newest line big, a few previous ones small
  function layout() {
    const items = [...log().children];
    while (items.length > 80) { const li = items.shift(); entries.delete(Number(li.dataset.id)); li.remove(); }
    const keep = S.history ? Math.max(1, S.lines + 1) : 1;
    items.forEach((li, i) => {
      const fromEnd = items.length - 1 - i;
      li.hidden = !(fromEnd < keep || li.classList.contains("live"));
      li.classList.toggle("latest", fromEnd === 0);
      li.classList.toggle("older", fromEnd > 0 && !li.classList.contains("live"));
    });
  }

  // in-game phone: a chat card on top of the conversation while the phone is on screen
  function onPhone(m) {
    const box = $("#gphone"), list = $("#gphone-list");
    if (!m.items || !m.items.length) { box.hidden = true; document.body.classList.remove("phone-on"); return; }
    $("#gphone-head").textContent = m.header || "";
    list.innerHTML = m.items.map(it => `<div class="pb ${it.kind === "reply" ? "reply" : it.mine ? "mine" : ""}">` +
      (it.name ? `<span class="pn">${esc(it.name)}</span>` : "") + `<span class="pt">${esc(it.text)}</span>` +
      (S.original ? `<span class="po">${esc(it.en)}</span>` : "") + `</div>`).join("");
    box.hidden = false; document.body.classList.add("phone-on");
    list.scrollTop = list.scrollHeight;
  }

  function armClear() {
    clearTimeout(clearTimer);
    document.body.classList.remove("faded");
    if (S.autoclear > 0) clearTimer = setTimeout(() => document.body.classList.add("faded"), S.autoclear * 1000);
  }

  function showStatus(m) {
    const b = $("#banner");
    const msg = m.message || (m.state === "stopped" ? t("st_stopped") : m.state === "waiting" ? t("st_waiting") : "");
    if (m.state === "running" && !m.message) { b.hidden = true; return; }
    if (!msg) { b.hidden = true; return; }
    b.textContent = msg; b.className = "banner warn"; b.hidden = false;
    $("#empty-text").textContent = m.state === "running" ? t("waiting") : msg;
  }

  // ------------------------------------------------------------------ speech
  let voices = [];
  function langOfText() { return S.lang === "hu" ? "hu" : (navigator.language || "en").slice(0, 2); }
  function fillVoices() {
    if (!("speechSynthesis" in window)) { $("#s-tts").disabled = true; return; }
    voices = speechSynthesis.getVoices();
    const sel = $("#s-voice"); sel.innerHTML = "";
    const want = (targetLang || langOfText()).slice(0, 2);
    const list = voices.filter(v => v.lang.toLowerCase().startsWith(want));
    sel.append(new Option(t("default_voice"), ""));
    list.forEach(v => sel.append(new Option(`${v.name}`, v.voiceURI)));
    sel.value = S.voice;
  }
  function unlockSpeech() { try { const u = new SpeechSynthesisUtterance(" "); u.volume = 0; speechSynthesis.speak(u); } catch {} }
  function speak(text, isUpdate, speaker) {
    if (!S.tts || !("speechSynthesis" in window) || !text) return;
    if (isUpdate && speechSynthesis.speaking && S.interrupt) return;
    if (S.interrupt) speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(S.speakName && speaker && !isUpdate ? `${speaker}: ${text}` : text);
    if (S.pitch && speaker) {        // stable, subtle pitch per speaker so voices are easier to tell apart
      let h = 0; for (const ch of speaker.toLowerCase()) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
      u.pitch = [1, 0.8, 1.2, 0.9, 1.1, 0.7, 1.3][h % 7];
    }
    const v = voices.find(v => v.voiceURI === S.voice) || voices.find(v => v.lang.toLowerCase().startsWith(targetLang));
    if (v) u.voice = v;
    u.lang = v?.lang || targetLang;
    u.rate = S.rate; u.volume = S.volume;
    speechSynthesis.speak(u);
  }
  if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = fillVoices;

  // ------------------------------------------------------------------ wake lock
  let wakeLock = null;
  async function updateWake() {
    const hint = $("#wake-hint");
    if (!S.wake) { wakeLock?.release(); wakeLock = null; hint.hidden = true; return; }
    if (!("wakeLock" in navigator)) { hint.textContent = t("wake_unsupported"); hint.hidden = false; return; }
    hint.hidden = true;
    try { if (!wakeLock && document.visibilityState === "visible") { wakeLock = await navigator.wakeLock.request("screen"); wakeLock.onrelease = () => { wakeLock = null; }; } }
    catch { hint.textContent = t("wake_unsupported"); hint.hidden = false; }
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") { updateWake(); if (!ws || ws.readyState > 1) connect(); }
  });

  // ------------------------------------------------------------------ chrome
  stage().addEventListener("scroll", () => { stick = atBottom(); if (stick) $("#jump").hidden = true; });
  $("#jump").onclick = () => { stick = true; scrollDown(true); $("#jump").hidden = true; };
  const openSheet = open => {
    $("#sheet").classList.toggle("open", open); $("#sheet").setAttribute("aria-hidden", String(!open));
    $("#sheet-backdrop").hidden = !open;
    if (open) fillVoices();
  };
  $("#btn-settings").onclick = () => openSheet(true);
  $("#sheet-close").onclick = () => openSheet(false);
  $("#sheet-backdrop").onclick = () => openSheet(false);
  $("#btn-tts").onclick = () => { S.tts = !S.tts; $("#s-tts").checked = S.tts; save(); apply(); onSetting("tts"); };
  const fsEl = root;
  if (!fsEl.requestFullscreen && !fsEl.webkitRequestFullscreen) $("#btn-full").hidden = true;
  $("#btn-full").onclick = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else (fsEl.requestFullscreen || fsEl.webkitRequestFullscreen).call(fsEl).catch?.(() => {});
  };
  $("#btn-forget").onclick = () => { localStorage.removeItem("sb.token"); token = ""; openSheet(false); authFailed = true; ws?.close(); showPair(""); setTimeout(() => authFailed = false, 100); };
  let idleTimer;
  const wake = () => { document.body.classList.remove("idle"); clearTimeout(idleTimer); idleTimer = setTimeout(() => document.body.classList.add("idle"), 4000); };
  ["pointerdown", "keydown"].forEach(e => addEventListener(e, wake)); wake();

  bind("#s-size", "size", "value", v => v); bind("#s-font", "font"); bind("#s-theme", "theme"); bind("#s-color", "color");
  bind("#s-align", "align"); bind("#s-original", "original", "checked"); bind("#s-history", "history", "checked");
  bind("#s-lines", "lines"); bind("#s-autoclear", "autoclear"); bind("#s-tts", "tts", "checked"); bind("#s-voice", "voice");
  bind("#s-rate", "rate", "value", v => Number(v).toFixed(1) + "×"); bind("#s-volume", "volume", "value", v => Math.round(v * 100) + "%");
  bind("#s-interrupt", "interrupt", "checked"); bind("#s-speakname", "speakName", "checked"); bind("#s-pitch", "pitch", "checked"); bind("#s-wake", "wake", "checked"); bind("#s-lang", "lang");

  applyI18n(); apply();
  if ("serviceWorker" in navigator && window.isSecureContext) navigator.serviceWorker.register("/sw.js").catch(() => {});

  fetch("/api/info").then(r => r.json()).then(info => {
    if (info.pin_required && !token) showPair(""); else { showApp(); connect(); }
  }).catch(() => { showApp(); connect(); });
})();
