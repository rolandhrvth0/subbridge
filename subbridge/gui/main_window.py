from __future__ import annotations

import logging
import time
import threading
from html import escape

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from ..branding import APP_NAME, VERSION
from ..capture import CaptureError, create_backend
from ..config import AppSettings, Profile
from ..engine import Callbacks, Engine
from ..i18n import set_language, tr
from ..paths import resource_dir
from ..server.net import lan_ip
from ..server.server import SubtitleServer
from ..translate.argos import PRECISE, download_model, download_precise, installed_models, precise_installed
from ..translate.registry import ONLINE
from . import theme
from .bridge import Bridge
from .help import HelpDialog
from .overlay import OverlayManager
from .settings_dialog import SettingsDialog
from .icons import icon
from .sources import best_source, list_sources
from .settings_dialog import LANGS
from .widgets import Card, FeatureTile, PreviewWidget, QrWidget, RegionSelector

ERR_KEYS = {"minimized": "err_minimized", "window_gone": "err_window_gone", "black": "err_black"}


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        set_language(settings.language)
        self.profile = settings.profile()
        self.bridge = Bridge()
        from ..capture.device import DeviceCapture, MultiCapture
        self.devices = DeviceCapture()
        try:
            platform_capture = create_backend()
            self._capture_error = ""
        except CaptureError as e:          # e.g. no X display: capture cards and the phone still work
            from ..capture.base import CaptureSource
            platform_capture, self._capture_error = CaptureSource(), str(e)
        self.capture = MultiCapture(platform_capture, self.devices)
        self.gameview = None
        self.server = self._make_server()
        from ..server.discovery import Announcer
        self.announcer = Announcer()
        self.engine = Engine(settings, self.capture, Callbacks(
            status=lambda s, m="", c="": self.bridge.status.emit(s, m, c),
            preview=lambda img, boxes: self.bridge.preview.emit(img, boxes),
            subtitle=self._on_engine_subtitle,
            stats=lambda d: self.bridge.stats.emit(d),
            overlay=lambda boxes: self.bridge.overlay.emit(boxes),
            phone=self._on_engine_phone))
        self.overlay = OverlayManager()
        from .phonepanel import PhonePanel
        self.phone_panel = PhonePanel()
        self.sources: list[dict] = []
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(resource_dir() / "server" / "web" / "icon-512.png")))
        self.resize(1200, 880)
        self.setMinimumSize(1000, 800)
        self._build()
        self._connect()
        self.apply_theme()
        if not self.server.start():
            self._show_alert(tr("err_port", e=self.server.error), "network")
        else:
            self._announce()
        self.refresh_sources(select_saved=True)
        if self._capture_error:
            self._show_alert(self._capture_error)
        self._update_phone()
        from ..remote import Remote
        self.remote = Remote(on_change=lambda: self.bridge.feed.emit())
        from ..updater import Updater
        self.updater = Updater(self.remote, on_ready=lambda: self.bridge.feed.emit())
        if settings.online_feed:
            self.remote.start()
        self._on_feed()
        self._fill_profiles()
        self._update_translator()
        self._preview_timer = QTimer(self, interval=700, timeout=self._idle_preview)
        self._preview_timer.start()
        self._autostart_pending = False
        self._sources_timer = QTimer(self, interval=3000, timeout=self._auto_refresh)
        self._sources_timer.start()
        self.btn_start.setFocus()

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 16, 22, 20)
        outer.setSpacing(14)

        # header
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(str(resource_dir() / "server" / "web" / "icon-192.png")).pixmap(30, 30))
        brand = QLabel(APP_NAME, objectName="brand")
        edition = QLabel(tr("edition"), objectName="edition")
        self.status_pill = QLabel(tr("stopped"), objectName="statusPill")
        head.addWidget(logo)
        head.addWidget(brand)
        head.addWidget(edition)
        head.addSpacing(8)
        head.addWidget(self.status_pill)
        head.addStretch(1)
        head.addWidget(QLabel(tr("profile"), objectName="muted"))
        self.cmb_profile = QComboBox(toolTip=tr("profile_tip"))
        self.cmb_profile.setMinimumWidth(170)
        head.addWidget(self.cmb_profile)
        self.btn_profile = QToolButton(toolTip=tr("profile_manage"))
        self.btn_profile.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        menu.addAction(tr("profile_new"), self.new_profile)
        menu.addAction(tr("profile_dup"), lambda: self.new_profile(copy=True))
        menu.addAction(tr("profile_rename"), self.rename_profile)
        menu.addSeparator()
        menu.addAction(tr("profile_delete"), self.delete_profile)
        self.btn_profile.setMenu(menu)
        self.btn_profile.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        head.addWidget(self.btn_profile)
        head.addSpacing(10)
        self.btn_lang = QToolButton(toolTip="Magyar / English")
        self.btn_lang.setText("EN" if self.settings.language == "hu" else "HU")
        self.btn_theme = QToolButton()
        self.btn_settings = QToolButton(toolTip=tr("settings"))
        self.btn_help = QToolButton(toolTip=tr("help"))
        self.btn_report = QToolButton(toolTip=tr("report"))
        self.btn_news = QToolButton(toolTip=tr("news"))
        self.btn_news.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        for b in (self.btn_lang, self.btn_theme, self.btn_news, self.btn_settings, self.btn_report, self.btn_help):
            b.setCursor(Qt.PointingHandCursor)
            head.addWidget(b)
        self.btn_start = QPushButton(tr("start"), objectName="primary")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setMinimumWidth(150)
        head.addSpacing(8)
        head.addWidget(self.btn_start)
        outer.addLayout(head)

        # alert
        self.alert = QFrame(objectName="alert")
        al = QHBoxLayout(self.alert)
        al.setContentsMargins(14, 10, 10, 10)
        self.alert_icon = QLabel()
        self.alert_text = QLabel(objectName="alertText", wordWrap=True)
        self.alert_help = QPushButton(tr("help"), objectName="ghost")
        al.addWidget(self.alert_icon)
        al.addWidget(self.alert_text, 1)
        al.addWidget(self.alert_help)
        self.alert.hide()
        outer.addWidget(self.alert)

        # feature tiles: the main things the app can do, one click each
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tile_overlay = FeatureTile("layers", tr("tile_overlay"))
        self.tile_gphone = FeatureTile("message", tr("tile_gphone"))
        self.tile_zones = FeatureTile("grid", tr("tile_zones"))
        self.tile_card = FeatureTile("video", tr("tile_card"))
        for t in (self.tile_overlay, self.tile_gphone, self.tile_zones, self.tile_card):
            tiles.addWidget(t, 1)
        outer.addLayout(tiles)

        cols = QHBoxLayout()
        cols.setSpacing(14)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.setSpacing(14)
        right.setSpacing(14)
        cols.addLayout(left, 1)
        cols.addLayout(right, 0)
        outer.addLayout(cols, 1)

        # source card
        src = Card(tr("source"))
        row = QHBoxLayout()
        self.cmb_source = QComboBox()
        self.cmb_source.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_refresh = QToolButton(toolTip=tr("refresh"))
        row.addWidget(self.cmb_source, 1)
        row.addWidget(self.btn_refresh)
        src.lay.addLayout(row)
        row2 = QHBoxLayout()
        self.btn_region = QPushButton(tr("select_region"))
        self.lbl_region = QLabel(objectName="small")
        row2.addWidget(self.btn_region)
        row2.addWidget(self.lbl_region, 1)
        self.btn_gameview = QPushButton(tr("game_view"))
        self.btn_gameview.setToolTip(tr("game_view_tip"))
        self.btn_gameview.hide()
        row2.addWidget(self.btn_gameview)
        src.lay.addLayout(row2)
        self.preview = PreviewWidget()
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        src.lay.addWidget(self.preview, 1)
        self.lbl_stats = QLabel(objectName="small")
        src.lay.addWidget(self.lbl_stats)
        self.lbl_ovstate = QLabel(objectName="small", wordWrap=True, textFormat=Qt.RichText)
        self.lbl_ovstate.hide()
        src.lay.addWidget(self.lbl_ovstate)
        orow = QHBoxLayout()
        self.chk_overlay = QCheckBox(tr("overlay_on"), toolTip=tr("overlay_tip"))
        self.lbl_overlay = QLabel(objectName="small", wordWrap=True)
        orow.addWidget(self.chk_overlay)
        orow.addWidget(self.lbl_overlay, 1)
        src.lay.addLayout(orow)
        self.chk_overlay.hide()
        self.lbl_overlay.hide()
        left.addWidget(src, 1)

        # phone card
        ph = Card(tr("phone"))
        self.qr = QrWidget()
        self.qr.setFixedSize(172, 172)
        qrow = QHBoxLayout()
        qrow.addStretch(1)
        qrow.addWidget(self.qr)
        qrow.addStretch(1)
        ph.lay.addLayout(qrow)
        ph.lay.addSpacing(4)
        hint = QLabel(tr("phone_hint"), objectName="muted", wordWrap=True, alignment=Qt.AlignCenter)
        ph.lay.addWidget(hint)
        urow = QHBoxLayout()
        self.lbl_url = QLabel(objectName="muted", textInteractionFlags=Qt.TextSelectableByMouse)
        self.btn_copy = QToolButton(toolTip=tr("copy"))
        urow.addStretch(1)
        urow.addWidget(self.lbl_url)
        urow.addWidget(self.btn_copy)
        urow.addStretch(1)
        ph.lay.addLayout(urow)
        prow = QHBoxLayout()
        pl = QLabel(tr("pin"), objectName="muted")
        self.lbl_pin = QLabel(objectName="pin", textInteractionFlags=Qt.TextSelectableByMouse)
        prow.addStretch(1)
        prow.addWidget(pl)
        prow.addSpacing(8)
        prow.addWidget(self.lbl_pin)
        prow.addStretch(1)
        ph.lay.addLayout(prow)
        self.lbl_clients = QLabel(tr("clients_none"), objectName="small", alignment=Qt.AlignCenter, wordWrap=True)
        ph.lay.addWidget(self.lbl_clients)
        ph.setFixedWidth(360)
        ph.setMinimumHeight(ph.sizeHint().height() + 10)     # never squeeze the QR code
        right.addWidget(ph)

        # translator card
        trc = Card(tr("translator"))
        self.cmb_engine = QComboBox()
        for k in ("argos", "deepl", "google", "libre"):
            self.cmb_engine.addItem(tr(f"engine_{k}"), k)
        trc.lay.addWidget(self.cmb_engine)
        self.ed_key = QLineEdit(echoMode=QLineEdit.Password)
        trc.lay.addWidget(self.ed_key)
        self.lbl_langs = QLabel(objectName="small")
        trc.lay.addWidget(self.lbl_langs)
        self.lbl_model = QLabel(objectName="small", wordWrap=True)
        self.btn_model = QPushButton(tr("download_model"))
        trc.lay.addWidget(self.lbl_model)
        self.lbl_tm = QLabel(objectName="small", wordWrap=True)
        trc.lay.addWidget(self.lbl_tm)
        trc.lay.addWidget(self.btn_model)
        self.prog = QProgressBar(textVisible=False, maximumHeight=8)
        self.prog.hide()
        trc.lay.addWidget(self.prog)
        self.lbl_privacy = QLabel(objectName="small", wordWrap=True)
        trc.lay.addWidget(self.lbl_privacy)
        trc.setFixedWidth(360)
        right.addWidget(trc)
        right.addStretch(1)

        # last subtitle card
        last = Card(tr("last"))
        self.lbl_log = QLabel("—", objectName="muted", wordWrap=True, textFormat=Qt.RichText)
        self.lbl_log.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.lbl_meta = QLabel(objectName="small")
        last.lay.addWidget(self.lbl_log, 1)
        lrow = QHBoxLayout()
        lrow.addWidget(self.lbl_meta, 1)
        self.btn_history = QPushButton(tr("history_open"))
        lrow.addWidget(self.btn_history)
        last.lay.addLayout(lrow)
        self.chk_learn = QCheckBox(tr("learn_mode"))
        self.chk_learn.setChecked(self.profile.learn_mode)
        last.lay.addWidget(self.chk_learn)
        self._log: dict[int, dict] = {}
        self.history: dict[int, dict] = {}            # every subtitle of this session (Subtitle history)
        last.setMinimumHeight(215)
        left.addWidget(last, 0)

        foot = QLabel(f"{APP_NAME} {VERSION}", objectName="small")
        outer.addWidget(foot, 0, Qt.AlignRight)

    def _connect(self):
        b = self.bridge
        b.status.connect(self._on_status)
        b.preview.connect(lambda img, boxes: self.preview.set_frame(img, boxes))
        b.subtitle.connect(self._on_subtitle)
        b.stats.connect(self._on_stats)
        b.clients.connect(self._on_clients)
        b.download.connect(self._on_download)
        b.download_done.connect(self._on_download_done)
        b.overlay.connect(self._route_overlay)
        self.btn_gameview.clicked.connect(self.open_gameview)
        b.ocr_ready.connect(self._on_ocr_ready)
        b.phone.connect(self._on_phone)
        self.chk_overlay.toggled.connect(self._on_overlay_toggled)
        self.tile_overlay.clicked.connect(lambda: self.chk_overlay.setChecked(not self.chk_overlay.isChecked()))
        self.tile_gphone.clicked.connect(self._toggle_gphone)
        self.tile_zones.clicked.connect(lambda: self.open_settings("zones"))
        self.tile_card.clicked.connect(self._card_tile)
        self.btn_start.clicked.connect(self.toggle_run)
        self.btn_refresh.clicked.connect(lambda: self.refresh_sources())
        self.cmb_source.activated.connect(self._on_source_changed)
        self.btn_region.clicked.connect(self.select_region)
        self.btn_copy.clicked.connect(self._copy_url)
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_lang.clicked.connect(self.toggle_language)
        self.btn_help.clicked.connect(lambda: HelpDialog(self).exec())
        self.btn_report.clicked.connect(self.open_report)
        self.btn_history.clicked.connect(self.open_history)
        self.chk_learn.toggled.connect(self._on_learn)
        self.btn_settings.clicked.connect(lambda: self.open_settings())
        self.btn_news.clicked.connect(self.open_news)
        b.feed.connect(self._on_feed)
        self.cmb_profile.activated.connect(lambda i: self.switch_profile(self.cmb_profile.itemText(i)))
        self.lbl_langs.linkActivated.connect(lambda _: self.open_settings("translate"))
        self.alert_help.clicked.connect(lambda: self.install_update() if self._alert_topic == "update_install"
                                        else self.open_report() if self._alert_topic == "report"
                                        else self.open_news() if self._alert_topic == "update"
                                        else HelpDialog(self, self._alert_topic).exec())
        self.cmb_engine.currentIndexChanged.connect(self._on_engine_changed)
        self.ed_key.editingFinished.connect(self._on_key_changed)
        self.btn_model.clicked.connect(self.download_model)
        self._alert_topic = ""

    # ------------------------------------------------------------------ theme / language
    def colors(self):
        return theme.DARK if self.settings.theme == "dark" else theme.LIGHT

    def apply_theme(self):
        c = self.colors()
        app = QApplication.instance()
        app.setPalette(theme.palette(c))
        app.setStyleSheet(theme.stylesheet(c))
        m = c["muted"]
        self.btn_theme.setIcon(icon("moon" if self.settings.theme == "light" else "sun", m))
        self.btn_help.setIcon(icon("help", m))
        self.btn_report.setIcon(icon("flag", m))
        self.btn_settings.setIcon(icon("settings", m))
        self.btn_news.setIcon(icon("bell", c["accent"] if getattr(self, "remote", None) and self.remote.unread else m))
        self.btn_profile.setIcon(icon("more", m))
        self.btn_refresh.setIcon(icon("refresh", m))
        self.btn_copy.setIcon(icon("copy", m, 16))
        self.btn_region.setIcon(icon("crop", c["text"], 16))
        self.alert_icon.setPixmap(icon("alert", c["warn"]).pixmap(20, 20))
        if hasattr(self, "tile_overlay"):
            self._update_tiles()
        self._update_start_button()

    def toggle_theme(self):
        self.settings.theme = "dark" if self.settings.theme == "light" else "light"
        self.settings.save()
        self.apply_theme()

    def toggle_language(self):
        self.settings.language = "en" if self.settings.language == "hu" else "hu"
        self.settings.save()
        QMessageBox.information(self, APP_NAME, "Restart the app to switch language. / Indítsd újra a nyelvváltáshoz."
                                if self.settings.language == "en" else
                                "Indítsd újra az alkalmazást a nyelvváltáshoz. / Restart to switch language.")

    # ------------------------------------------------------------------ sources
    def refresh_sources(self, select_saved=False):
        try:
            self.sources = list_sources(self.capture)
        except CaptureError as e:
            self._show_alert(str(e))
            self.sources = []
        self.cmb_source.clear()
        c = self.colors()["muted"]
        for s in self.sources:
            self.cmb_source.addItem(icon("window" if s["kind"] == "window" else "monitor", c, 16), s["label"])
        idx = None
        p = self.profile
        if p.source_kind == "window" and p.window_title and not any(
                s["kind"] == "window" and (s["title"] == p.window_title or p.window_title.lower() in s["title"].lower()
                                          or s["title"].lower() in p.window_title.lower()) for s in self.sources):
            # the saved window (e.g. the Remote Play app) is not open yet: keep waiting for it instead of
            # silently switching to another source
            self.sources.insert(0, {"kind": "window", "ident": None, "title": p.window_title, "stream": True,
                                    "waiting": True, "label": tr("source_waiting", name=p.window_title)})
            self.cmb_source.insertItem(0, icon("window", c, 16), self.sources[0]["label"])
        if p.source_kind == "device" and p.device_name and not any(
                s["kind"] == "device" and (s["ident"] == p.device_id or s["title"] == p.device_name)
                for s in self.sources):
            # the capture card is not plugged in yet: wait for it (picked up as soon as it appears)
            # instead of silently switching to the desktop
            self.sources.insert(0, {"kind": "device", "ident": None, "title": p.device_name, "stream": True,
                                    "waiting": True, "label": tr("source_waiting_card", name=p.device_name)})
            self.cmb_source.insertItem(0, icon("monitor", c, 16), self.sources[0]["label"])
        if p.source_kind:
            for i, s in enumerate(self.sources):
                if p.source_kind == "window" and s["kind"] == "window" and s["title"] == p.window_title:
                    idx = i
                    break
                if p.source_kind == "device" and s["kind"] == "device" and (
                        s["ident"] == p.device_id or s["title"] == p.device_name or s.get("waiting")):
                    idx = i
                    break
                if p.source_kind == "screen" and s["kind"] == "screen" and s["ident"] == p.screen_index:
                    idx = i if idx is None else idx
            if p.source_kind == "window" and idx is None and p.window_title:
                low = p.window_title.lower()
                for i, s in enumerate(self.sources):
                    if s["kind"] == "window" and (low in s["title"].lower() or s["title"].lower() in low):
                        idx = i
                        break
        if idx is None:
            idx = best_source(self.sources)
        self._source_keys = self._keys()
        if self.sources:
            self.cmb_source.setCurrentIndex(idx)
            self._apply_source(self.sources[idx], save=False)
        self._update_region_label()

    def _keys(self):
        return [(s["kind"], s["ident"], s["title"]) for s in self.sources if not s.get("waiting")]

    def _auto_refresh(self):
        """Windows come and go (the Remote Play app starts together with us): keep the list current and
        switch to the saved window as soon as it appears."""
        if self.cmb_source.view().isVisible():
            return                                     # the user is choosing right now
        try:
            fresh = list_sources(self.capture)
        except CaptureError:
            return
        self._card_watch()
        if [(s["kind"], s["ident"], s["title"]) for s in fresh] == getattr(self, "_source_keys", None):
            return
        # a capture card that was unplugged: drop its dead session, so plugging it back in (often under
        # the same /dev/videoN) opens it fresh
        present = {str(s["ident"]) for s in fresh if s["kind"] == "device"}
        for k in [k for k in self.devices.sessions if k not in present]:
            if self.gameview:
                self.gameview.close()
            self.devices.sessions.pop(k).close()
        cur = self.current_source()
        waiting = bool(cur and cur.get("waiting"))
        self.refresh_sources(select_saved=True)
        now = self.current_source()
        if waiting and now and not now.get("waiting") and now["kind"] == "window":
            self.engine.window_id = now["ident"]
            if self._autostart_pending and not self.engine.running:
                self.toggle_run()
        elif waiting and now and not now.get("waiting") and now["kind"] == "device":
            if self._autostart_pending and not self.engine.running:
                self.toggle_run()
        self._update_tiles()

    def _card_watch(self):
        """Capture card stream died (console rest mode, HDMI mode switch, USB reset): restart it in place."""
        if self.profile.source_kind != "device":
            return
        sess = self.devices.sessions.get(self.profile.device_id)
        if sess is None or not sess.stalled():
            return
        if sess._restarts >= 3 and not getattr(sess, "_reopened", False):
            # in-place stop/start did not bring the picture back: close the card and open it fresh
            logging.getLogger(__name__).info("capture card: still no frames, reopening the device")
            self.reopen_device()
            new = self.devices.sessions.get(self.profile.device_id)
            if new is not None:
                new._reopened = True
            return
        if sess.restart():
            logging.getLogger(__name__).info("capture card: no frames, stream restarted (try %d)", sess._restarts)

    def _update_overlay_ui(self):
        p = self.profile
        win = p.source_kind in ("window", "device")
        self.chk_overlay.blockSignals(True)
        self.chk_overlay.setChecked(p.overlay)
        self.chk_overlay.setEnabled(win)
        self.chk_overlay.blockSignals(False)
        self.lbl_overlay.setText(tr("overlay_hint_device") if p.source_kind == "device"
                                 else tr("overlay_hint") if win else tr("overlay_need_window"))
        self.overlay.scale = p.overlay_scale
        self._update_tiles()

    def _update_tiles(self):
        p, c = self.profile, self.colors()
        win = p.source_kind in ("window", "device")
        if not win:
            self.tile_overlay.set_state("disabled", tr("tile_overlay_need"), c)
        else:
            self.tile_overlay.set_state("on" if p.overlay else "off",
                                        tr("tile_on_game") if p.overlay else tr("tile_off"), c)
        self.tile_gphone.set_state("on" if p.game_phone else "off",
                                   tr("tile_gphone_on") if p.game_phone else tr("tile_off"), c)
        n = sum(1 for z in p.zones if z.get("on", True))
        self.tile_zones.set_state("on" if n else "action", tr("tile_zones_n", n=n) if n else tr("tile_zones_add"), c)
        if p.source_kind == "device":
            self.tile_card.set_state("on", tr("tile_card_open"), c)
        else:
            self.tile_card.set_state("action", tr("tile_card_how"), c)

    def _toggle_gphone(self):
        self.profile.game_phone = not self.profile.game_phone
        self._save_profile()
        self._update_tiles()
        if not self.profile.game_phone:
            self._on_phone(None)
        if self.engine.running:
            self.engine.start(self.engine.window_id)

    def _card_tile(self):
        if self.profile.source_kind == "device":
            self.open_gameview()
        else:
            HelpDialog(self, "capture_card").exec()

    def _on_overlay_toggled(self, on):
        self.profile.overlay = on
        self._save_profile()
        self._update_tiles()
        if not on:
            self.overlay.clear()
        if self.engine.running:          # the loop reads the flag at start
            self.engine.start(self.engine.window_id)

    def _on_source_changed(self, i):
        if 0 <= i < len(self.sources):
            self._apply_source(self.sources[i])

    def _open_device(self, dev_id: str | None):
        """Keep exactly the selected capture device open (it is shared with the Game View)."""
        from ..capture.device import DeviceSession
        for k in list(self.devices.sessions):
            if k != dev_id:
                if self.gameview:
                    self.gameview.close()
                self.devices.sessions.pop(k).close()
        if dev_id and dev_id not in self.devices.sessions:
            p = self.profile
            try:
                sess = self.devices.sessions[dev_id] = DeviceSession(dev_id, p.device_audio_id, False, p.device_format,
                                                                               p.low_latency)
                if sess.usb2:
                    self._show_alert(tr("err_card_usb2"), "capture_card")
            except CaptureError as e:
                self._show_alert(str(e), "capture_card")

    def reopen_device(self):
        """Format or audio input changed in the settings."""
        if self.profile.source_kind != "device":
            return
        was = self.engine.running
        if was:
            self.engine.stop()
        if self.gameview:
            self.gameview.close()
        self._open_device(None)
        self._open_device(self.profile.device_id)
        if was:
            self.toggle_run()

    def open_gameview(self):
        from .gameview import GameView
        sess = self.devices.sessions.get(self.profile.device_id)
        if not sess:
            return
        if self.gameview is None:
            def closed():
                sess.set_audio(self.profile.device_audio_id, False)
                self.gameview = None
            self.gameview = None
            try:
                from .gameview_gpu import GpuGameView, gpu_available
                if gpu_available():
                    self.gameview = GpuGameView(sess, on_close=closed, mode=self.profile.framegen,
                                                low_latency=self.profile.low_latency)
            except Exception:  # noqa: BLE001  – no Qt Quick / GPU: the classic view still works
                import logging
                logging.getLogger(__name__).exception("GPU Game View failed, using the classic one")
                self.gameview = None
            if self.gameview is None:
                sess.framegen_wanted = self.profile.framegen == "builtin"
                self.gameview = GameView(sess, on_close=closed)
            self.gameview.scale = self.profile.overlay_scale
            sess.set_audio(self.profile.device_audio_id, self.profile.device_audio)
        self.gameview.show()
        self.gameview.raise_()
        self.gameview.activateWindow()

    def _on_engine_phone(self, state):
        if state:
            self.server.publish({k: v for k, v in state.items() if k in ("type", "header", "items")})
        else:
            self.server.publish({"type": "phone", "items": []})
        self.bridge.phone.emit(state)

    def _on_phone(self, state):
        from PySide6.QtCore import QRect
        if self.profile.source_kind == "device":
            self.phone_panel.show_state(None, QRect(), QRect())
            if self.gameview:
                self.gameview.show_phone(state if self.profile.overlay else None)
            return
        if not state or not self.profile.overlay or self.profile.source_kind != "window":
            self.phone_panel.show_state(None, QRect(), QRect())
            return
        scr = QGuiApplication.primaryScreen()
        dpr = scr.devicePixelRatio() if scr else 1.0
        fx, fy, fw, fh = state["frame"]
        x0, y0, x1, y1 = state["rect"]
        self.phone_panel.show_state(state, QRect(int(fx / dpr), int(fy / dpr), int(fw / dpr), int(fh / dpr)),
                                    QRect(int(x0 / dpr), int(y0 / dpr), int((x1 - x0) / dpr), int((y1 - y0) / dpr)))

    def _route_overlay(self, boxes):
        if self.profile.source_kind == "device":
            if self.gameview:
                self.gameview.update_boxes(boxes if self.profile.overlay else [])
        else:
            self.overlay.update(boxes)

    def _apply_source(self, s, save=True):
        p = self.profile
        if s.get("waiting"):
            self.engine.window_id = None              # the engine finds the window by its title once it opens
            self.btn_gameview.setVisible(False)
            self._update_region_label()
            return
        p.source_kind = s["kind"]
        self._open_device(s["ident"] if s["kind"] == "device" else None)
        self.btn_gameview.setVisible(s["kind"] == "device")
        if s["kind"] == "device":
            p.device_id, p.device_name = s["ident"], s["title"]
        elif s["kind"] == "window":
            p.window_title = s["title"]
            self.engine.window_id = s["ident"]
        else:
            p.screen_index = int(s["ident"])
        if save:
            self._save_profile()
        self._update_region_label()
        self._update_overlay_ui()

    def current_source(self):
        i = self.cmb_source.currentIndex()
        return self.sources[i] if 0 <= i < len(self.sources) else None

    def grab_source(self, full=True):
        s = self.current_source()
        if not s:
            return None
        if s.get("waiting"):
            raise CaptureError(tr("err_window_gone"), "window_gone")
        return self.capture.grab(s["kind"], s["ident"])

    def select_region(self):
        try:
            img = self.grab_source()
        except CaptureError as e:
            self._show_alert(self._err_text(e.code, str(e)), e.code)
            return
        if img is None:
            return
        self.hide() if self.current_source()["kind"] == "screen" else None
        dlg = RegionSelector(img, self.profile.region)
        ok = dlg.exec()
        self.show()
        if ok and dlg.result_region:
            self.profile.region = [round(v, 4) for v in dlg.result_region]
            self._save_profile()
            self._update_region_label()
            self._idle_preview(force=True)
        return ok

    def _update_region_label(self):
        s = self.current_source()
        try:
            if s and not s.get("waiting"):
                sw, sh = self.capture.source_size(s["kind"], s["ident"])
                fx, fy, fw, fh = self.profile.region
                self.lbl_region.setText(tr("region_set", w=int(fw * sw), h=int(fh * sh)))
                return
        except CaptureError:
            pass
        self.lbl_region.setText(tr("region_missing"))

    def _idle_preview(self, force=False):
        """When not running, still show what the region currently contains."""
        if self.engine.running and not force:
            return
        s = self.current_source()
        if not s or not self.isVisible():
            return
        if s.get("waiting"):
            self.preview.clear_frame(tr("source_waiting", name=s["title"]))
            return
        try:
            sw, sh = self.capture.source_size(s["kind"], s["ident"])
            fx, fy, fw, fh = self.profile.region
            img = self.capture.grab(s["kind"], s["ident"], (int(fx * sw), int(fy * sh), int(fw * sw), int(fh * sh)))
            self.preview.set_frame(img, [])
            if self.alert.isVisible() and self._alert_topic in ERR_KEYS:
                self.alert.hide()
        except CaptureError as e:
            self.preview.clear_frame(self._err_text(e.code, str(e)))

    # ------------------------------------------------------------------ profile / translator
    def _save_profile(self):
        self.settings.save_profile(self.profile)
        self.settings.active_profile = self.profile.name
        self.settings.save()
        self.engine.profile = self.profile

    def _update_translator(self):
        p = self.profile
        self.cmb_engine.blockSignals(True)
        self.cmb_engine.setCurrentIndex(max(0, self.cmb_engine.findData(p.engine)))
        self.cmb_engine.blockSignals(False)
        key = {"deepl": ("deepl_key", tr("deepl_key")), "google": ("google_key", tr("google_key")),
               "libre": ("libre_url", tr("libre_url"))}.get(p.engine)
        self.ed_key.setVisible(bool(key))
        if key:
            self.ed_key.setPlaceholderText(key[1])
            self.ed_key.setEchoMode(QLineEdit.Normal if p.engine == "libre" else QLineEdit.Password)
            self.ed_key.setText(getattr(self.settings, key[0]))
        names = {c: (hu if self.settings.language == "hu" else en) for c, hu, en in LANGS}
        self.lbl_langs.setText(f'{names.get(p.source_lang, p.source_lang)} → {names.get(p.target_lang, p.target_lang)}'
                               f' · <a href="#" style="color:{self.colors()["accent"]}">{tr("change")}</a>')
        models = installed_models()
        have = (p.source_lang, p.target_lang) in models or (
            (p.source_lang, "en") in models and ("en", p.target_lang) in models)
        if hasattr(self, "chk_learn"):
            self.chk_learn.blockSignals(True)
            self.chk_learn.setChecked(p.learn_mode)
            self.chk_learn.blockSignals(False)
        pair = (p.source_lang, p.target_lang)
        precise = precise_installed(*pair)
        can_precise = have and not precise and pair in PRECISE and p.engine == "argos"
        self.lbl_model.setText(tr("model_precise") if precise else
                               tr("model_std", mb=PRECISE[pair]["size_mb"]) if can_precise else
                               tr("model_ok") if have else tr("model_missing"))
        self.lbl_model.setVisible(p.engine == "argos" or not have)
        from ..translate.memory import memory
        n_tm = memory().count(p.target_lang) if p.source_lang == "en" else 0
        self.lbl_tm.setText(tr("tm_info", n=f"{n_tm:,}".replace(",", "\u202f")))
        self.lbl_tm.setVisible(n_tm > 0)
        self.btn_model.setVisible(not have or can_precise)
        self.btn_model.setText(tr("precise_get") if can_precise else tr("download_model"))
        self.btn_model.setIcon(icon("download", self.colors()["text"], 16))
        self.lbl_privacy.setText(tr("privacy_online", engine=self.cmb_engine.currentText().split(" (")[0])
                                 if p.engine in ONLINE else tr("privacy_offline"))

    def _on_engine_changed(self, _i):
        self.profile.engine = self.cmb_engine.currentData()
        self._save_profile()
        self._update_translator()

    def _on_key_changed(self):
        attr = {"deepl": "deepl_key", "google": "google_key", "libre": "libre_url"}.get(self.profile.engine)
        if attr:
            setattr(self.settings, attr, self.ed_key.text().strip())
            self.settings.save()

    def download_model(self):
        p = self.profile
        self.btn_model.setEnabled(False)
        self.prog.show()
        self.prog.setValue(0)

        def run():
            try:
                models = installed_models()
                pair = (p.source_lang, p.target_lang)
                if pair in models and pair in PRECISE and not precise_installed(*pair):
                    download_precise(*pair, progress=lambda d, t: self.bridge.download.emit(d, t))
                    self.engine._argos._models.pop(pair, None)      # use the new model from the next line on
                    self.bridge.download_done.emit("")
                    return
                pairs = [(p.source_lang, p.target_lang)]
                if p.source_lang != "en" and p.target_lang != "en":
                    pairs = [(s, t) for s, t in ((p.source_lang, "en"), ("en", p.target_lang)) if (s, t) not in models]
                for s_, t_ in pairs:
                    download_model(s_, t_, lambda d, t: self.bridge.download.emit(d, t))
                self.bridge.download_done.emit("")
            except Exception as e:  # noqa: BLE001
                self.bridge.download_done.emit(str(e))
        threading.Thread(target=run, daemon=True).start()

    def _on_download(self, done, total):
        if total:
            self.prog.setMaximum(100)
            self.prog.setValue(int(done * 100 / total))
            self.lbl_model.setText(tr("downloading", p=int(done * 100 / total)))

    def _on_download_done(self, err):
        self.prog.hide()
        self.btn_model.setEnabled(True)
        if err:
            self.lbl_model.setText(err)
        else:
            self._update_translator()

    # ------------------------------------------------------------------ profiles / settings
    def _fill_profiles(self):
        self.cmb_profile.blockSignals(True)
        self.cmb_profile.clear()
        self.cmb_profile.addItems(self.settings.profile_names())
        self.cmb_profile.setCurrentText(self.profile.name)
        self.cmb_profile.blockSignals(False)

    def switch_profile(self, name: str, save_current: bool = True):
        if name == self.profile.name:
            return
        if save_current:
            self._save_profile()
        was = self.engine.running
        if was:
            self.engine.stop()
        self.settings.active_profile = name
        self.profile = self.settings.profile(name)
        self.settings.save()
        self.engine.profile = self.profile
        self._fill_profiles()
        self.overlay.clear()
        self.refresh_sources(select_saved=True)
        self._update_translator()
        self._idle_preview(force=True)
        if was:
            self.toggle_run()

    def _ask_name(self, title, value=""):
        name, ok = QInputDialog.getText(self, title, tr("profile_name"), text=value)
        name = name.strip()
        if not ok or not name:
            return None
        if name in self.settings.profile_names() and name != value:
            QMessageBox.warning(self, title, tr("profile_exists"))
            return None
        return name

    def new_profile(self, copy=False):
        name = self._ask_name(tr("profile_dup") if copy else tr("profile_new"))
        if not name:
            return
        self._save_profile()
        if copy:
            p = Profile.from_dict(dict(self.profile.__dict__))
            p.name = name
        else:      # a new game: keep the chosen source, everything else default
            p = Profile(name=name, source_kind=self.profile.source_kind, window_title=self.profile.window_title,
                        screen_index=self.profile.screen_index, engine=self.profile.engine)
        self.settings.save_profile(p)
        self.settings.save()
        self.switch_profile(name)

    def rename_profile(self):
        old = self.profile.name
        name = self._ask_name(tr("profile_rename"), old)
        if not name or name == old:
            return
        self.settings.profiles = [q for q in self.settings.profiles if q.get("name") != old]
        self.profile.name = name
        self._save_profile()
        self._fill_profiles()

    def delete_profile(self):
        if len(self.settings.profiles) < 2:
            QMessageBox.information(self, APP_NAME, tr("profile_last"))
            return
        if QMessageBox.question(self, APP_NAME, tr("profile_delete_q", name=self.profile.name)) != QMessageBox.Yes:
            return
        old = self.profile.name
        self.settings.delete_profile(old)
        self.switch_profile(self.settings.profile_names()[0], save_current=False)

    def _on_feed(self):
        n = self.remote.unread
        self.btn_news.setText(f" {n}" if n else "")
        self.btn_news.setIcon(icon("bell", self.colors()["accent"] if n or self.remote.update_available()
                                   else self.colors()["muted"]))
        if self.remote.update_available():
            v = self.remote.latest.get("version", "")
            if self.updater.supported():                 # installed app: download + verify in the background
                if self.updater.ready_path and self.updater.ready_version == v:
                    self._show_alert(tr("update_ready", v=v), "update_install")
                else:
                    self.updater.start_download()
            elif not self.alert.isVisible():
                self._show_alert(tr("update_banner", v=v), "update")

    def install_update(self):
        if self.engine.running:
            self.engine.stop()
            self._update_start_button()
        if self.updater.install(restart=True):
            self._update_on_close = False
            self.close()
            QApplication.instance().quit()
        elif self.updater.error:
            self._show_alert(tr("update_failed", e=self.updater.error), "update")

    def open_news(self):
        from .news import NewsDialog
        NewsDialog(self).exec()
        self._on_feed()

    def open_settings(self, page: str = ""):
        SettingsDialog(self, page).exec()

    def show_wizard(self):
        from .wizard import Wizard
        if Wizard(self).exec() and not self.engine.running:
            self.toggle_run()

    def apply_settings(self, p: Profile, net_changed: bool, lang_changed: bool):
        was = self.engine.running
        if was:
            self.engine.stop()
        self.profile = p
        self._save_profile()
        self._update_overlay_ui()
        self.apply_theme()
        self._update_translator()
        if net_changed:
            self.restart_server()
        if lang_changed:
            QMessageBox.information(self, APP_NAME, tr("restart_lang"))
        if was:
            self.toggle_run()

    def _make_server(self):
        st = self.settings
        ctx = None
        if st.https:
            try:
                from ..server.tls import ssl_context
                ctx = ssl_context(lan_ip())
            except Exception as e:  # noqa: BLE001
                st.https = False
                self._show_alert(tr("err_https", e=e))
        srv = SubtitleServer(st.port, st.pin, st.token, st.require_pin, ssl_context=ctx)
        srv.on_clients_changed = lambda n, names: self.bridge.clients.emit(n, names)
        return srv

    def _announce(self):
        threading.Thread(target=self.announcer.start, args=(lan_ip(), self.settings.port, self.settings.https,
                                                            self.settings.require_pin), daemon=True).start()

    def restart_server(self):
        old = self.server
        old.stop()
        self.server = self._make_server()
        self.server.lines, self.server.visible = old.lines, old.visible
        if not self.server.start():
            self._show_alert(tr("err_port", e=self.server.error), "network")
        else:
            self.alert.hide()
            self._announce()
        self._update_phone()
        self._on_clients(0, [])

    # ------------------------------------------------------------------ phone
    def phone_url(self) -> str:
        proto = "https" if self.settings.https else "http"
        return f"{proto}://{lan_ip()}:{self.settings.port}/"

    def _update_phone(self):
        url = self.phone_url()
        self.qr.set_data(f"{url}?k={self.settings.token}")
        self.lbl_url.setText(url.rstrip("/"))
        self.lbl_pin.setText(f"{self.settings.pin[:3]} {self.settings.pin[3:]}")

    def _copy_url(self):
        QGuiApplication.clipboard().setText(self.phone_url())
        self.btn_copy.setToolTip(tr("copied"))

    def _on_clients(self, n, names):
        self.lbl_clients.setText(tr("clients_n", n=n, names=", ".join(names)) if n else tr("clients_none"))

    # ------------------------------------------------------------------ run
    def toggle_run(self):
        if self.engine.running:
            self.engine.stop()
        else:
            if not self.ensure_game_setup():
                return
            self._save_profile()
            s = self.current_source()
            self.engine.start(s["ident"] if s and s["kind"] == "window" else None)
            self._on_status("running", "", "")
        self._update_start_button()

    def ensure_game_setup(self) -> bool:
        """Before the first start: the animated 'set up the subtitles in the game' step (must be confirmed)."""
        if self.settings.game_setup_done:
            return True
        from .game_setup import GameSetupDialog
        self.showNormal()
        self.raise_()
        if not GameSetupDialog(self, self.colors()["accent"]).exec():
            return False
        self.settings.game_setup_done = True
        self.settings.save()
        return True

    def _update_start_button(self):
        run = self.engine.running
        c = self.colors()
        self.btn_start.setText(tr("stop") if run else tr("start"))
        self.btn_start.setObjectName("danger" if run else "primary")
        self.btn_start.setIcon(icon("stop" if run else "play", "#ffffff" if run else c["accent_ink"], 16))
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)

    def _err_text(self, code, fallback):
        if self.profile.source_kind == "device" and code in ("black", "no_signal"):
            return tr("err_card_black")
        return tr(ERR_KEYS[code]) if code in ERR_KEYS else fallback

    def _show_alert(self, text, topic=""):
        self._alert_topic = topic
        self.alert_text.setText(text)
        self.alert_help.setText(tr("report") if topic == "report" else tr("help"))
        self.alert.show()

    def _fetch_ocr_data(self):
        if getattr(self, "_ocr_dl", False):
            return
        self._ocr_dl = True
        self._show_alert(tr("ocr_downloading"))
        lang = self.profile.source_lang

        def run():
            from ..ocr.tesseract import download_tessdata
            try:
                download_tessdata(lang)
                self.bridge.ocr_ready.emit("")
            except Exception as e:  # noqa: BLE001
                self.bridge.ocr_ready.emit(str(e))
        threading.Thread(target=run, daemon=True).start()

    def _on_ocr_ready(self, err):
        self._ocr_dl = False
        if err:
            self._show_alert(tr("ocr_download_failed", e=err))
        else:
            self.alert.hide()
            if not self.engine.running:
                self.toggle_run()

    def _on_status(self, state, message, code):
        if code == "no_ocr_data":
            self._fetch_ocr_data()
            return
        self.status_pill.setText(tr(state) if state in ("running", "stopped", "waiting") else tr("waiting"))
        self.status_pill.setProperty("state", state)
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)
        if message:
            self._show_alert(self._err_text(code, message), code)
        if state == "stopped":
            self.lbl_ovstate.hide()
        elif state in ("running", "stopped"):
            self.alert.hide()
        self.server.publish({"type": "status", "state": state, "message": self._err_text(code, message) if message else ""})
        self._update_start_button()

    def _on_engine_subtitle(self, msg):
        self.server.publish(msg)
        self.bridge.subtitle.emit(msg)

    def _refresh_history(self):
        self._hist_pending = False
        if getattr(self, "_history_dlg", None) is not None:
            self._history_dlg.refresh()

    def _on_learn(self, on):
        self.profile.learn_mode = on
        self._save_profile()

    def open_history(self):
        from .history import HistoryDialog
        if getattr(self, "_history_dlg", None) is None:
            self._history_dlg = HistoryDialog(self)
            self._history_dlg.finished.connect(lambda _r: setattr(self, "_history_dlg", None))
        self._history_dlg.refresh()
        self._history_dlg.show()
        self._history_dlg.raise_()

    def _on_subtitle(self, msg):
        if msg.get("type") != "line":
            return
        h = self.history.setdefault(msg["id"], {"_t": time.time()})
        h.update(msg)
        if len(self.history) > 3000:
            self.history.pop(next(iter(self.history)))
        if getattr(self, "_history_dlg", None) is not None and not getattr(self, "_hist_pending", False):
            self._hist_pending = True                     # refresh the open history at most twice a second
            QTimer.singleShot(500, self._refresh_history)
        self._log[msg["id"]] = msg
        for k in sorted(self._log)[:-3]:
            self._log.pop(k)
        c = self.colors()
        rows = []
        ids = sorted(self._log)
        for i in ids:
            m = self._log[i]
            last = i == ids[-1]
            label = m.get("zone_name") or (tr(f"zone_{m['zone']}") if m.get("zone") else m.get("speaker"))
            col_who = self._speaker_color(m.get("speaker")) if m.get("speaker") and not m.get("zone") else c["accent"]
            who = f'<span style="color:{col_who};font-weight:650">{escape(label)}</span>&nbsp; ' if label else ""
            size = 16 if last else 13
            col = c["text"] if last else c["muted"]
            rows.append(f'<div style="margin-bottom:6px">{who}<span style="font-size:{size}px;color:{col};'
                        f'font-weight:{600 if last else 450}">{escape(m["text"])}</span><br>'
                        f'<span style="font-size:12px;color:{c["muted"]}">{escape(m["original"])}</span></div>')
        self.lbl_log.setText("".join(rows))
        eng = {"argos": "Offline", "own": tr("history_own").capitalize(), "deepl": "DeepL", "google": "Google Cloud", "libre": "LibreTranslate",
               "none": "—"}.get(msg.get("engine"), msg.get("engine", ""))
        self.lbl_meta.setText(f"{eng} · {tr('latency')}: {msg.get('latency_ms', 0)} ms")

    HUES = [38, 205, 140, 330, 265, 15, 175, 85, 300, 230]      # same order as the phone page

    def _speaker_color(self, name: str) -> str:
        from PySide6.QtGui import QColor
        hues = self.__dict__.setdefault("_hues", {})
        k = name.lower()
        if k not in hues:
            used = set(hues.values())
            hues[k] = next((h for h in self.HUES if h not in used), self.HUES[len(hues) % len(self.HUES)])
        dark = self.settings.theme == "dark"
        return QColor.fromHsl(hues[k], int(255 * (0.75 if dark else 0.65)), int(255 * (0.66 if dark else 0.38))).name()

    OV_COLORS = {"ok": "#3fb950", "ok_textless": "#3fb950", "reading": "#3fb950", "no_subtitle": "#d29922", "covered": "#d29922",
                 "no_window": "#f85149", "error": "#f85149"}

    def _on_stats(self, d):
        self.lbl_stats.setText(f"{d['fps']:.1f} {tr('fps')} · {tr('ocr_time')} {d['ocr_ms']:.0f} ms")
        self._show_ov_state(d.get("overlay"))

    def _show_ov_state(self, h):
        """Live line under the preview: does the overlay see a subtitle – and if not, why."""
        if h not in self.OV_COLORS:
            self.lbl_ovstate.hide()
            return
        self.lbl_ovstate.setText(f'<span style="color:{self.OV_COLORS[h]}">&#9679;</span>&nbsp; {tr("ov_" + h)}')
        self.lbl_ovstate.show()
        if h == "error" and not getattr(self, "_report_offered", False) and not self.alert.isVisible():
            self._report_offered = True                  # once per session: offer a one-click report
            self._show_alert(tr("report_offer"), "report")

    def open_report(self, note: str = ""):
        from .report_dialog import ReportDialog
        ReportDialog(self, note if isinstance(note, str) else "").exec()

    # ------------------------------------------------------------------ lifecycle
    def closeEvent(self, e):
        from ..updater import platform_key
        if getattr(self, "_update_on_close", True) and platform_key() == "windows" and self.updater.ready_path:
            self.updater.install(restart=False)          # Windows: install silently once the app is closed
        self.overlay.clear()
        self.phone_panel.close()
        if self.gameview:
            self.gameview.close()
        self._open_device(None)
        self.engine.shutdown()
        self.announcer.stop()
        self.server.stop()
        self._save_profile()
        super().closeEvent(e)

    def open_url(self, url):
        QDesktopServices.openUrl(QUrl(url))
