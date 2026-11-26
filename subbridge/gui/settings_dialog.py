"""Settings dialog: sidebar + pages. Profile pages edit the active game profile, the rest are app-wide.
Nothing is applied until "Save"; every field has a one-line plain-language hint."""
from __future__ import annotations

import secrets

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPushButton, QScrollArea,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..config import Profile
from ..i18n import tr
from ..ocr import ocr_engines
from ..translate.argos import installed_models
from ..translate.registry import ONLINE

LANGS = [("en", "Angol", "English"), ("hu", "Magyar", "Hungarian"), ("de", "Német", "German"),
         ("fr", "Francia", "French"), ("es", "Spanyol", "Spanish"), ("it", "Olasz", "Italian"),
         ("pt", "Portugál", "Portuguese"), ("pl", "Lengyel", "Polish"), ("nl", "Holland", "Dutch"),
         ("cs", "Cseh", "Czech"), ("sk", "Szlovák", "Slovak"), ("ro", "Román", "Romanian"),
         ("ru", "Orosz", "Russian"), ("uk", "Ukrán", "Ukrainian"), ("tr", "Török", "Turkish"),
         ("ja", "Japán", "Japanese"), ("ko", "Koreai", "Korean"), ("zh", "Kínai", "Chinese")]
STAGES = ["keep", "before", "after"]


FIELD_W = 380


def _hint(text: str, width: int = FIELD_W) -> QLabel:
    lb = QLabel(text, objectName="small", wordWrap=True)
    lb.setFixedWidth(width)
    _fit(lb)
    return lb


def _fit(lb: QLabel):
    """Form layouts get the height of wrapped labels wrong; reserve it explicitly."""
    lb.ensurePolished()
    lb.setMinimumHeight(lb.heightForWidth(lb.width()) + 2)


class SettingsDialog(QDialog):
    def __init__(self, main, page: str = ""):
        super().__init__(main)
        self.main = main
        self.st = main.settings
        self.p: Profile = Profile.from_dict(dict(main.profile.__dict__))
        self.hu = self.st.language == "hu"
        self.setWindowTitle(tr("settings"))
        self.resize(860, 620)
        self.setMinimumSize(760, 520)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        body = QHBoxLayout()
        body.setSpacing(0)
        lay.addLayout(body, 1)

        self.nav = QListWidget(objectName="nav")
        self.nav.setFixedWidth(210)
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.pages = QStackedWidget()
        body.addWidget(self.nav)
        body.addWidget(self.pages, 1)

        self._ids: list[str] = []
        self._add("ocr", tr("s_ocr"), self._page_ocr())
        self._add("filter", tr("s_filter"), self._page_filter())
        self._add("translate", tr("s_translate"), self._page_translate())
        self._add("overlay", tr("s_overlay"), self._page_overlay())
        self._add("zones", tr("s_zones"), self._page_zones())
        self._add("card", tr("s_card"), self._page_card())
        self._add("glossary", tr("s_glossary"), self._page_glossary())
        self._add("network", tr("s_network"), self._page_network())
        self._add("general", tr("s_general"), self._page_general())
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(self._ids.index(page) if page in self._ids else 0)

        foot = QHBoxLayout()
        foot.setContentsMargins(20, 12, 20, 16)
        self.lbl_profile = QLabel(tr("s_profile_note", name=self.p.name), objectName="small")
        foot.addWidget(self.lbl_profile, 1)
        cancel = QPushButton(tr("cancel"))
        save = QPushButton(tr("save"), objectName="primary")
        save.setDefault(True)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)
        foot.addWidget(cancel)
        foot.addWidget(save)
        lay.addLayout(foot)

    # ------------------------------------------------------------------ helpers
    def _add(self, ident, title, widget):
        self._ids.append(ident)
        self.nav.addItem(QListWidgetItem(title))
        sc = QScrollArea(widgetResizable=True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setWidget(widget)
        self.pages.addWidget(sc)

    def _page(self, title: str, sub: str = ""):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(28, 22, 28, 22)
        v.setSpacing(6)
        v.addWidget(QLabel(title, objectName="h2"))
        if sub:
            v.addWidget(QLabel(sub, objectName="small", wordWrap=True))
        f = QFormLayout()
        f.setContentsMargins(0, 14, 0, 0)
        f.setHorizontalSpacing(18)
        f.setVerticalSpacing(4)
        f.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        f.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        v.addLayout(f)
        v.addStretch(1)
        return w, v, f

    @staticmethod
    def _row(f: QFormLayout, label: str, field, hint: str = ""):
        if isinstance(field, QWidget) and not isinstance(field, QCheckBox):
            field.setFixedWidth(FIELD_W)
        f.addRow(label, field)
        if hint:
            f.addRow("", _hint(hint))
        f.addRow(QLabel(fixedHeight=8))

    def _lang_combo(self, value: str) -> QComboBox:
        cb = QComboBox()
        for code, hu, en in LANGS:
            cb.addItem(hu if self.hu else en, code)
        cb.setCurrentIndex(max(0, cb.findData(value)))
        return cb

    @staticmethod
    def _choice(values, current, fmt=str, special=None) -> QComboBox:
        """Preset values instead of free number fields: nothing to mistype."""
        vals = list(values)
        if current not in vals and current != 0:
            vals = sorted(vals + [current])
        cb = QComboBox()
        if special is not None:
            cb.addItem(special, 0)
        for v in vals:
            cb.addItem(fmt(v), v)
        cb.setCurrentIndex(max(0, cb.findData(current)))
        return cb

    # ------------------------------------------------------------------ pages
    def _page_ocr(self):
        w, _, f = self._page(tr("s_ocr"), tr("s_ocr_sub"))
        p = self.p
        self.cmb_ocr = QComboBox()
        engines = ocr_engines()
        for k, name in engines.items():
            self.cmb_ocr.addItem(tr(f"ocr_{k}") if tr(f"ocr_{k}") != f"ocr_{k}" else name, k)
        self.cmb_ocr.setCurrentIndex(max(0, self.cmb_ocr.findData(p.ocr_engine)))
        self._row(f, tr("s_ocr_engine"), self.cmb_ocr, tr("s_ocr_engine_hint"))
        self.sp_interval = self._choice([150, 200, 250, 350, 500, 750, 1000], p.interval_ms, lambda v: f"{v} ms")
        self._row(f, tr("s_interval"), self.sp_interval, tr("s_interval_hint"))
        self.cmb_color = QComboBox()
        for k in ("light", "yellow", "dark", "any"):
            self.cmb_color.addItem(tr(f"color_{k}"), k)
        self.cmb_color.setCurrentIndex(max(0, self.cmb_color.findData(p.text_color)))
        self._row(f, tr("s_text_color"), self.cmb_color)
        self.chk_box = QCheckBox(tr("s_find_box"), checked=p.find_box)
        self._row(f, "", self.chk_box, tr("s_find_box_hint"))
        self.sp_conf = self._choice(range(20, 95, 10), p.min_confidence, lambda v: f"{v} %")
        self._row(f, tr("s_min_conf"), self.sp_conf, tr("s_min_conf_hint"))
        self.sp_thr = self._choice(range(100, 241, 20), p.threshold, special=tr("auto"))
        self._row(f, tr("s_threshold"), self.sp_thr, tr("s_threshold_hint"))
        self.sp_scale = self._choice([1.0, 1.5, 2.0, 2.5, 3.0], p.scale, lambda v: f"{v:g}×", special=tr("auto"))
        self._row(f, tr("s_scale"), self.sp_scale)
        self.chk_invert = QCheckBox(tr("s_invert"), checked=p.invert)
        self._row(f, "", self.chk_invert)
        return w

    def _page_filter(self):
        w, _, f = self._page(tr("s_filter"), tr("s_filter_sub"))
        p = self.p
        self.sp_stable = self._choice(range(1, 6), p.stable_frames)
        self._row(f, tr("s_stable"), self.sp_stable, tr("s_stable_hint"))
        self.sp_sim = self._choice(range(70, 96, 5), round(p.similarity * 100), lambda v: f"{v} %")
        self._row(f, tr("s_similarity"), self.sp_sim, tr("s_similarity_hint"))
        self.chk_speaker = QCheckBox(tr("s_split_speaker"), checked=p.split_speaker)
        self._row(f, "", self.chk_speaker, tr("s_split_speaker_hint"))
        return w

    def _page_translate(self):
        w, v, f = self._page(tr("s_translate"), tr("s_translate_sub"))
        p = self.p
        self.cmb_src = self._lang_combo(p.source_lang)
        self.cmb_tgt = self._lang_combo(p.target_lang)
        self._row(f, tr("s_source_lang"), self.cmb_src, tr("s_source_lang_hint"))
        self._row(f, tr("s_target_lang"), self.cmb_tgt)
        self.cmb_tr = QComboBox()
        for k in ("argos", "deepl", "google", "libre"):
            self.cmb_tr.addItem(tr(f"engine_{k}"), k)
        self.cmb_tr.setCurrentIndex(max(0, self.cmb_tr.findData(p.engine)))
        self._row(f, tr("s_engine"), self.cmb_tr)
        self.lbl_engine_info = _hint("")
        self.lbl_engine_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f.addRow("", self.lbl_engine_info)
        f.addRow(QLabel(fixedHeight=8))

        self.ed_deepl = QLineEdit(self.st.deepl_key, echoMode=QLineEdit.Password, placeholderText="xxxxxxxx-…:fx")
        self.ed_google = QLineEdit(self.st.google_key, echoMode=QLineEdit.Password, placeholderText="AIza…")
        self.ed_libre_url = QLineEdit(self.st.libre_url, placeholderText="http://localhost:5000")
        self.ed_libre_key = QLineEdit(self.st.libre_key, echoMode=QLineEdit.Password, placeholderText=tr("optional"))
        self._key_rows = {}
        for k, label, field in (("deepl", tr("deepl_key"), self.ed_deepl),
                                ("google", tr("google_key"), self.ed_google),
                                ("libre", tr("libre_url"), self.ed_libre_url),
                                ("libre2", tr("libre_key"), self.ed_libre_key)):
            lb = QLabel(label)
            field.setFixedWidth(FIELD_W)
            f.addRow(lb, field)
            self._key_rows[k] = (lb, field)
        f.addRow(QLabel(fixedHeight=8))

        cache = self.main.engine.cache
        row = QHBoxLayout()
        self.lbl_cache = QLabel(tr("cache_n", n=len(cache)), objectName="small")
        btn = QPushButton(tr("cache_clear"), objectName="ghost")
        btn.clicked.connect(lambda: (cache.clear(), self.lbl_cache.setText(tr("cache_n", n=0))))
        row.addWidget(self.lbl_cache, 1)
        row.addWidget(btn)
        box = QWidget()
        box.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        box.setFixedWidth(FIELD_W)
        f.addRow(tr("cache"), box)
        f.addRow("", _hint(tr("cache_hint")))

        self.cmb_tr.currentIndexChanged.connect(self._update_engine_rows)
        self.cmb_src.currentIndexChanged.connect(self._update_engine_rows)
        self.cmb_tgt.currentIndexChanged.connect(self._update_engine_rows)
        self._update_engine_rows()
        return w

    def _update_engine_rows(self):
        e = self.cmb_tr.currentData()
        show = {"deepl": e == "deepl", "google": e == "google", "libre": e == "libre", "libre2": e == "libre"}
        for k, (lb, field) in self._key_rows.items():
            lb.setVisible(show[k])
            field.setVisible(show[k])
        if e == "argos":
            src, tgt = self.cmb_src.currentData(), self.cmb_tgt.currentData()
            have = (src, tgt) in installed_models() or (
                (src, "en") in installed_models() and ("en", tgt) in installed_models())
            info = tr("engine_info_argos") + " " + (tr("model_ok") if have else tr("model_missing_hint"))
        else:
            info = tr(f"engine_info_{e}")
        if e in ONLINE:
            info += " " + tr("privacy_online", engine=self.cmb_tr.currentText().split(" (")[0])
        self.lbl_engine_info.setText(info)
        _fit(self.lbl_engine_info)

    def _page_overlay(self):
        w, _, f = self._page(tr("s_overlay"), tr("s_overlay_sub"))
        self.chk_ov = QCheckBox(tr("overlay_on"), checked=self.p.overlay)
        self._row(f, "", self.chk_ov, tr("overlay_hint"))
        self.chk_gphone = QCheckBox(tr("game_phone_on"), checked=self.p.game_phone)
        self._row(f, "", self.chk_gphone, tr("game_phone_hint"))
        self.cmb_ov_size = self._choice([0.85, 1.0, 1.15, 1.3, 1.5], self.p.overlay_scale, lambda v: f"{round(v * 100)} %")
        self._row(f, tr("s_overlay_size"), self.cmb_ov_size, tr("s_overlay_size_hint"))
        return w

    ZONE_PRESETS = {"help": [0.01, 0.02, 0.36, 0.3], "objective": [0.15, 0.84, 0.7, 0.12],
                     "notice": [0.62, 0.02, 0.37, 0.25], "other": [0.3, 0.3, 0.4, 0.3]}

    def _page_zones(self):
        w, v, _ = self._page(tr("s_zones"), tr("s_zones_sub"))
        self.zones = [dict(z) for z in self.p.zones]
        self.zone_tbl = QTableWidget(0, 4)
        self.zone_tbl.setHorizontalHeaderLabels([tr("z_on"), tr("z_kind"), tr("z_name"), tr("z_area")])
        hh = self.zone_tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.zone_tbl.verticalHeader().hide()
        self.zone_tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.zone_tbl.setMinimumHeight(220)
        v.insertWidget(v.count() - 1, self.zone_tbl, 1)
        row = QHBoxLayout()
        add = QPushButton(tr("z_add"))
        menu = QMenu(add)
        for k in ("help", "objective", "notice", "other"):
            menu.addAction(tr(f"zone_{k}_long"), lambda k=k: self._zone_add(k))
        add.setMenu(menu)
        rem = QPushButton(tr("g_remove"), objectName="ghost")
        rem.clicked.connect(self._zone_remove)
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        v.insertLayout(v.count() - 1, row)
        v.insertWidget(v.count() - 1, _hint(tr("z_hint"), 540))
        self._zone_fill()
        return w

    def _zone_fill(self):
        t = self.zone_tbl
        t.setRowCount(0)
        for i, z in enumerate(self.zones):
            t.insertRow(i)
            chk = QCheckBox(checked=z.get("on", True))
            chk.toggled.connect(lambda on, z=z: z.__setitem__("on", on))
            cell = QWidget()
            hl = QHBoxLayout(cell)
            hl.setContentsMargins(10, 0, 4, 0)
            hl.addWidget(chk)
            t.setCellWidget(i, 0, cell)
            cb = QComboBox()
            for k in ("help", "objective", "notice", "other"):
                cb.addItem(tr(f"zone_{k}"), k)
            cb.setCurrentIndex(max(0, cb.findData(z.get("kind", "other"))))
            cb.currentIndexChanged.connect(lambda _i, z=z, cb=cb: z.__setitem__("kind", cb.currentData()))
            t.setCellWidget(i, 1, cb)
            it = QTableWidgetItem(z.get("name", ""))
            t.setItem(i, 2, it)
            btn = QPushButton(tr("z_pick"), objectName="ghost")
            btn.clicked.connect(lambda _c=False, z=z: self._zone_pick(z))
            t.setCellWidget(i, 3, btn)
        t.itemChanged.connect(self._zone_renamed)

    def _zone_renamed(self, it):
        if it.column() == 2 and it.row() < len(self.zones):
            self.zones[it.row()]["name"] = it.text().strip()

    def _zone_add(self, kind):
        self.zones.append({"name": "", "kind": kind, "region": list(self.ZONE_PRESETS[kind]), "on": True})
        self._zone_fill()
        self._zone_pick(self.zones[-1])

    def _zone_remove(self):
        rows = sorted({ix.row() for ix in self.zone_tbl.selectedIndexes()}, reverse=True)
        for r in rows:
            if r < len(self.zones):
                self.zones.pop(r)
        self._zone_fill()

    def _zone_pick(self, z):
        from ..capture import CaptureError
        from .widgets import RegionSelector
        try:
            img = self.main.grab_source()
        except CaptureError as e:
            QMessageBox.warning(self, tr("s_zones"), str(e))
            return
        if img is None:
            return
        dlg = RegionSelector(img, z.get("region"))
        if dlg.exec() and dlg.result_region:
            z["region"] = [round(v, 4) for v in dlg.result_region]

    def _update_signal(self, sess):
        try:
            i = sess.signal_info()
        except RuntimeError:                       # session closed meanwhile
            self._signal_timer.stop()
            return
        if not i["live"] or not i["size"]:
            text = tr("card_signal_none")
        else:
            text = tr("card_signal_live", w=i["size"][0], h=i["size"][1], fps=i["fps"] or "…")
            if i["range"] == "limited":
                text += "\n" + tr("card_range_limited")
        if self.lbl_signal.text() != text:
            self.lbl_signal.setText(text)
            _fit(self.lbl_signal)

    def _page_card(self):
        w, _, f = self._page(tr("s_card"), tr("s_card_sub"))
        sess = self.main.devices.sessions.get(self.p.device_id) if self.p.source_kind == "device" else None
        self.cmb_fmt = QComboBox()
        self.cmb_fmt.addItem(tr("card_fmt_auto") + (f"  ({sess.format.split(':')[0]})" if sess and not self.p.device_format else ""), "")
        for k in (sess.formats if sess else []):
            res, rest = k.split("@")
            fps, pix = rest.split(":")
            self.cmb_fmt.addItem(f"{res.replace('x', '×')}  ·  {fps} fps  ·  {pix}", k)
        self.cmb_fmt.setCurrentIndex(max(0, self.cmb_fmt.findData(self.p.device_format)))
        self._row(f, tr("card_fmt"), self.cmb_fmt, tr("card_fmt_hint") if sess else tr("card_none"))
        if sess is not None:
            self.lbl_signal = _hint("", FIELD_W)
            self._row(f, tr("card_signal"), self.lbl_signal)
            self._signal_timer = QTimer(self, interval=1000, timeout=lambda: self._update_signal(sess))
            self._signal_timer.start()
            self._update_signal(sess)
        from ..capture.device import list_audio_inputs, list_audio_outputs
        self.cmb_audio = QComboBox()
        self.cmb_audio.addItem(tr("card_audio_auto"), "")
        for a in list_audio_inputs():
            self.cmb_audio.addItem(a["name"], a["id"])
        self.cmb_audio.setCurrentIndex(max(0, self.cmb_audio.findData(self.p.device_audio_id)))
        self._row(f, tr("card_audio"), self.cmb_audio)
        self.cmb_audio_out = QComboBox()
        self.cmb_audio_out.addItem(tr("card_audio_out_default"), "")
        for a in list_audio_outputs():
            self.cmb_audio_out.addItem(a["name"], a["id"])
        self.cmb_audio_out.setCurrentIndex(max(0, self.cmb_audio_out.findData(self.p.device_audio_out)))
        self._row(f, tr("card_audio_out"), self.cmb_audio_out)
        self.chk_card_sound = QCheckBox(tr("card_sound"), checked=self.p.device_audio)
        self._row(f, "", self.chk_card_sound, tr("card_sound_hint"))
        self.chk_ll = QCheckBox(tr("card_ll"), checked=self.p.low_latency)
        self._row(f, "", self.chk_ll, tr("card_ll_hint"))
        from .. import fgmodes
        fi = fgmodes.info()
        self.cmb_fg = QComboBox()
        for k in fi.choices():
            self.cmb_fg.addItem(tr(f"fg_{k}") if k != "off" else tr("fg_offopt"), k)
        self.cmb_fg.setCurrentIndex(max(0, self.cmb_fg.findData(self.p.framegen)))
        self._row(f, tr("fg_mode"), self.cmb_fg, tr("fg_mode_hint"))
        self.cmb_fgx = QComboBox()
        for m in (2, 3, 4):
            self.cmb_fgx.addItem(tr(f"fg_x{m}"), m)
        self.cmb_fgx.setCurrentIndex(max(0, self.cmb_fgx.findData(self.p.fg_multiplier)))
        self.cmb_fgx.setEnabled("lsfg" in fi.choices())
        self._row(f, tr("fg_x"), self.cmb_fgx, tr("fg_x_hint"))
        self.chk_up = QCheckBox(tr("up_on"), checked=self.p.upscale)
        self._row(f, "", self.chk_up, tr("up_hint"))
        from .. import neural
        self.chk_nr = None
        if neural.available():                       # only on a machine with a local sb-nr install
            self.chk_nr = QCheckBox(tr("nr_on"), checked=self.p.neural)
            self._row(f, "", self.chk_nr, tr("nr_hint"))
            self.cmb_nr_style = QComboBox()
            for k in (1, 2, 0):
                self.cmb_nr_style.addItem(tr(f"nr_style{k}"), k)
            self.cmb_nr_style.setCurrentIndex(max(0, self.cmb_nr_style.findData(self.p.nr_style)))
            self._row(f, tr("nr_style"), self.cmb_nr_style)
            self.cmb_nr_int = QComboBox()
            for v in (0.25, 0.5, 0.75, 1.0):
                self.cmb_nr_int.addItem(f"{int(v * 100)} %", v)
            self.cmb_nr_int.setCurrentIndex(max(0, self.cmb_nr_int.findData(self.p.nr_intensity)))
            self._row(f, tr("nr_int"), self.cmb_nr_int)
            self.chk_nr_skin = QCheckBox(tr("nr_skin"), checked=self.p.nr_skin)
            self._row(f, "", self.chk_nr_skin, tr("nr_skin_hint"))
            self.chk_nr_stable = QCheckBox(tr("nr_stable"), checked=self.p.nr_stable)
            self._row(f, "", self.chk_nr_stable, tr("nr_stable_hint"))
        return w

    def _page_glossary(self):
        w, v, _ = self._page(tr("s_glossary"), tr("s_glossary_sub"))
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels([tr("g_type"), tr("g_find"), tr("g_replace")])
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl.verticalHeader().hide()
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setMinimumHeight(260)
        for r in self.p.glossary:
            self._add_rule(r)
        v.insertWidget(v.count() - 1, self.tbl, 1)
        row = QHBoxLayout()
        add = QPushButton(tr("g_add"))
        rem = QPushButton(tr("g_remove"), objectName="ghost")
        add.clicked.connect(lambda: (self._add_rule({}), self.tbl.editItem(self.tbl.item(self.tbl.rowCount() - 1, 1))))
        rem.clicked.connect(lambda: [self.tbl.removeRow(i) for i in sorted(
            {ix.row() for ix in self.tbl.selectedIndexes()}, reverse=True)])
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        v.insertLayout(v.count() - 1, row)
        v.insertWidget(v.count() - 1, _hint(tr("g_examples")))
        return w

    def _add_rule(self, r: dict):
        i = self.tbl.rowCount()
        self.tbl.insertRow(i)
        cb = QComboBox()
        for k in STAGES:
            cb.addItem(tr(f"g_{k}"), k)
        cb.setCurrentIndex(max(0, cb.findData(r.get("stage", "keep"))))
        self.tbl.setCellWidget(i, 0, cb)
        self.tbl.setItem(i, 1, QTableWidgetItem(r.get("find", "")))
        self.tbl.setItem(i, 2, QTableWidgetItem(r.get("replace", "")))

    def _glossary(self) -> list[dict]:
        out = []
        for i in range(self.tbl.rowCount()):
            find = (self.tbl.item(i, 1).text() if self.tbl.item(i, 1) else "").strip()
            if not find:
                continue
            stage = self.tbl.cellWidget(i, 0).currentData()
            rep = (self.tbl.item(i, 2).text() if self.tbl.item(i, 2) else "").strip()
            out.append({"find": find, "replace": "" if stage == "keep" else rep, "stage": stage,
                        "whole_word": True, "case_sensitive": False})
        return out

    def _page_network(self):
        w, _, f = self._page(tr("s_network"), tr("s_network_sub"))
        st = self.st
        self.sp_port = QLineEdit(str(st.port))
        self.sp_port.setValidator(QIntValidator(1024, 65535))
        self._row(f, tr("s_port"), self.sp_port, tr("s_port_hint"))
        self.chk_pin = QCheckBox(tr("s_require_pin"), checked=st.require_pin)
        self._row(f, "", self.chk_pin, tr("s_require_pin_hint"))
        self._new_pin = None
        row = QHBoxLayout()
        self.lbl_pin = QLabel(f"{st.pin[:3]} {st.pin[3:]}", objectName="h2")
        btn = QPushButton(tr("new_pin_btn"))
        btn.clicked.connect(self._regen)
        row.addWidget(self.lbl_pin)
        row.addSpacing(12)
        row.addWidget(btn)
        row.addStretch(1)
        self._row(f, tr("pin"), row, tr("new_pin_hint"))
        self.chk_https = QCheckBox(tr("s_https"), checked=st.https)
        self._row(f, "", self.chk_https, tr("s_https_hint"))
        return w

    def _regen(self):
        self._new_pin = (f"{secrets.randbelow(10**6):06d}", secrets.token_urlsafe(12))
        pin = self._new_pin[0]
        self.lbl_pin.setText(f"{pin[:3]} {pin[3:]}")

    def _page_general(self):
        w, _, f = self._page(tr("s_general"))
        self.cmb_lang = QComboBox()
        self.cmb_lang.addItem("Magyar", "hu")
        self.cmb_lang.addItem("English", "en")
        self.cmb_lang.setCurrentIndex(max(0, self.cmb_lang.findData(self.st.language)))
        self._row(f, tr("s_ui_lang"), self.cmb_lang, tr("s_ui_lang_hint"))
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItem(tr("theme_light"), "light")
        self.cmb_theme.addItem(tr("theme_dark"), "dark")
        self.cmb_theme.setCurrentIndex(max(0, self.cmb_theme.findData(self.st.theme)))
        self._row(f, tr("s_theme"), self.cmb_theme)
        self.chk_feed = QCheckBox(tr("s_feed"), checked=self.st.online_feed)
        self._row(f, "", self.chk_feed, tr("s_feed_hint"))
        btn = QPushButton(tr("wizard_again"))
        btn.clicked.connect(self._wizard)
        self._row(f, "", btn)
        return w

    def _wizard(self):
        self.reject()
        self.main.show_wizard()

    # ------------------------------------------------------------------ save
    def _save(self):
        p, st = self.p, self.st
        p.ocr_engine = self.cmb_ocr.currentData()
        p.interval_ms = self.sp_interval.currentData() if self.sp_interval.currentData() is not None else p.interval_ms
        p.text_color = self.cmb_color.currentData()
        p.find_box = self.chk_box.isChecked()
        p.min_confidence = self.sp_conf.currentData() if self.sp_conf.currentData() is not None else p.min_confidence
        p.threshold = self.sp_thr.currentData() if self.sp_thr.currentData() is not None else p.threshold
        p.scale = float(self.sp_scale.currentData())
        p.invert = self.chk_invert.isChecked()
        p.stable_frames = self.sp_stable.currentData() if self.sp_stable.currentData() is not None else p.stable_frames
        p.similarity = self.sp_sim.currentData() / 100
        p.split_speaker = self.chk_speaker.isChecked()
        p.source_lang = self.cmb_src.currentData()
        p.target_lang = self.cmb_tgt.currentData()
        if p.source_lang == p.target_lang:
            QMessageBox.warning(self, tr("settings"), tr("same_lang"))
            self.nav.setCurrentRow(self._ids.index("translate"))
            return
        p.engine = self.cmb_tr.currentData()
        p.glossary = self._glossary()
        p.overlay = self.chk_ov.isChecked()
        p.game_phone = self.chk_gphone.isChecked()
        p.zones = [z for z in self.zones if len(z.get("region", [])) == 4]
        card_changed = ((self.cmb_fmt.currentData(), self.cmb_audio.currentData(), self.cmb_audio_out.currentData())
                        != (p.device_format, p.device_audio_id, p.device_audio_out))
        p.device_format = self.cmb_fmt.currentData() or ""
        p.device_audio_id = self.cmb_audio.currentData() or ""
        p.device_audio_out = self.cmb_audio_out.currentData() or ""
        p.device_audio = self.chk_card_sound.isChecked()
        p.framegen = self.cmb_fg.currentData() or "auto"
        p.fg_multiplier = int(self.cmb_fgx.currentData() or 2)
        p.upscale = self.chk_up.isChecked()
        if self.chk_nr is not None:
            p.neural = self.chk_nr.isChecked()
            p.nr_style = int(self.cmb_nr_style.currentData())
            p.nr_intensity = float(self.cmb_nr_int.currentData())
            p.nr_skin = self.chk_nr_skin.isChecked()
            p.nr_stable = self.chk_nr_stable.isChecked()
        card_changed = card_changed or p.low_latency != self.chk_ll.isChecked()   # format choice depends on it
        p.low_latency = self.chk_ll.isChecked()
        p.overlay_scale = float(self.cmb_ov_size.currentData() or 1.0)

        net_before = (st.port, st.require_pin, st.https, st.pin, st.token)
        st.deepl_key = self.ed_deepl.text().strip()
        st.google_key = self.ed_google.text().strip()
        st.libre_url = self.ed_libre_url.text().strip()
        st.libre_key = self.ed_libre_key.text().strip()
        st.port = int(self.sp_port.text()) if self.sp_port.hasAcceptableInput() else st.port
        st.require_pin = self.chk_pin.isChecked()
        st.https = self.chk_https.isChecked()
        if self._new_pin:
            st.pin, st.token = self._new_pin
        lang_changed = self.cmb_lang.currentData() != st.language
        st.language = self.cmb_lang.currentData()
        st.theme = self.cmb_theme.currentData()
        st.online_feed = self.chk_feed.isChecked()
        self.main.apply_settings(p, net_changed=net_before != (st.port, st.require_pin, st.https, st.pin, st.token),
                                 lang_changed=lang_changed)
        if card_changed:
            self.main.reopen_device()
        self.accept()
