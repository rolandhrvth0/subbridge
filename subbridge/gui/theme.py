from PySide6.QtGui import QColor, QPalette

# Apple-like system palette (neutral greys, lots of air) with SubBridge's sunset pink → orange as the accent.
LIGHT = dict(bg="#f5f5f7", bg2="#ebebef", surface="#ffffff", surface2="#f2f2f5", line="#e2e2e7", text="#1d1d1f",
             muted="#6e6e73", accent="#ff2d55", accent_hover="#e8244b", accent2="#ff9500", accent_ink="#ffffff",
             ok="#34c759", warn="#ff9500", danger="#ff3b30", sel="#ffe4ea", side="#ececf0", sidesel="#ffffff")
DARK = dict(bg="#101012", bg2="#16161a", surface="#1c1c1f", surface2="#2a2a2e", line="#2e2e33", text="#f5f5f7",
            muted="#98989f", accent="#ff375f", accent_hover="#ff5579", accent2="#ff9f0a", accent_ink="#ffffff",
            ok="#30d158", warn="#ff9f0a", danger="#ff453a", sel="#3a1a24", side="#17171a", sidesel="#2a2a2e")


def rgba(hex_colour: str, alpha: int) -> str:
    """Qt style sheets read #RRGGBBAA as #AARRGGBB – use rgba() for translucent colours."""
    h = hex_colour.lstrip("#")
    return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {alpha})"


def stylesheet(c: dict) -> str:
    from ..paths import resource_dir
    check = (resource_dir() / "assets" / "ui" / f"check-{c['accent_ink'].lstrip('#')}.svg").as_posix()
    return f"""
* {{ font-family: "Inter Variable", "Inter", "SF Pro Text", "Segoe UI", sans-serif; font-size: 13.5px; color: {c['text']}; }}
QMainWindow, QDialog {{ background: {c['bg']}; }}
#root, #content {{ background: {c['bg']}; }}
QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['line']}; padding: 6px 9px; border-radius: 8px; }}

/* sidebar */
#sidebar {{ background: {c['side']}; border-right: 1px solid {c['line']}; }}
#brand {{ font-size: 17px; font-weight: 750; letter-spacing: -0.2px; }}
#version {{ color: {c['muted']}; font-size: 11.5px; }}
#navBtn {{ text-align: left; padding: 8px 12px; border: 0; border-radius: 9px; background: transparent; font-weight: 550; color: {c['text']}; }}
#navBtn:hover {{ background: {c['surface2']}; }}
#navBtn:checked {{ background: {c['sidesel']}; color: {c['text']}; font-weight: 650; }}
#navSection {{ color: {c['muted']}; font-size: 11px; font-weight: 650; padding: 10px 12px 2px 12px; }}
#gameChip {{ text-align: left; padding: 8px 10px; border: 1px solid {c['line']}; border-radius: 12px; background: {c['surface']}; font-weight: 650; }}
#gameChip:hover {{ border-color: {c['muted']}; }}

/* page */
#pageTitle {{ font-size: 28px; font-weight: 750; letter-spacing: -0.6px; }}
#pageSub {{ color: {c['muted']}; font-size: 14px; }}
#h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }}
#h2 {{ font-size: 16px; font-weight: 650; }}
#muted, QLabel[muted="true"] {{ color: {c['muted']}; }}
#small {{ color: {c['muted']}; font-size: 12px; }}
#groupTitle {{ color: {c['muted']}; font-size: 12px; font-weight: 600; padding-left: 4px; }}
#group, #card {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 14px; }}
#cardTitle {{ font-size: 12px; font-weight: 650; color: {c['muted']}; }}
#rowTitle {{ font-weight: 600; font-size: 14px; }}
#rowSub {{ color: {c['muted']}; font-size: 12.5px; }}
#rowSep {{ background: {c['line']}; max-height: 1px; min-height: 1px; }}
#rowIcon {{ border-radius: 8px; }}
#pin {{ font-size: 30px; font-weight: 700; letter-spacing: 6px; }}
#subHu {{ font-size: 18px; font-weight: 600; }}
#subEn {{ color: {c['muted']}; font-size: 13px; }}
#edition {{ color: {c['accent']}; font-size: 11.5px; font-weight: 650; }}
#speaker {{ color: {c['accent']}; font-weight: 650; font-size: 12px; }}
#preview {{ background: #000; border: 0; border-radius: 12px; color: {c['muted']}; }}
#codeBox {{ background: {c['surface2']}; border: 1px solid {c['line']}; border-radius: 9px; padding: 8px 10px; font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace; font-size: 12.5px; }}

/* status */
#statusPill {{ border-radius: 11px; padding: 3px 10px; font-weight: 600; font-size: 12px; background: {c['surface2']}; color: {c['muted']}; }}
#statusPill[state="running"] {{ background: {rgba(c['ok'], 36)}; color: {c['ok']}; }}
#statusPill[state="waiting"] {{ background: {rgba(c['warn'], 38)}; color: {c['warn']}; }}
#statusPill[state="error"] {{ background: {rgba(c['danger'], 34)}; color: {c['danger']}; }}
#alert {{ background: {rgba(c['warn'], 24)}; border: 1px solid {rgba(c['warn'], 85)}; border-radius: 12px; }}
#alertText {{ color: {c['text']}; }}

/* buttons */
QPushButton {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 9px; padding: 7px 14px; font-weight: 600; }}
QPushButton:hover {{ background: {c['surface2']}; }}
QPushButton:pressed {{ background: {c['line']}; }}
QPushButton:disabled {{ color: {c['muted']}; }}
QPushButton#primary {{ background: {c['accent']}; color: {c['accent_ink']}; border: 0; border-radius: 12px; padding: 11px 26px; font-size: 15px; font-weight: 700; }}
QPushButton#primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#primary:disabled {{ background: {c['surface2']}; color: {c['muted']}; }}
QPushButton#danger {{ background: {c['danger']}; color: #fff; border: 0; border-radius: 12px; padding: 10px 26px; font-size: 15px; font-weight: 700; }}
QPushButton#link {{ background: transparent; border: 0; color: {c['accent']}; padding: 4px 2px; font-weight: 600; }}
QPushButton#link:hover {{ text-decoration: underline; }}
QPushButton#ghost, QToolButton {{ background: transparent; border: 0; border-radius: 8px; padding: 6px; }}
QPushButton#ghost:hover, QToolButton:hover {{ background: {c['surface2']}; }}

/* inputs */
QComboBox, QLineEdit, QSpinBox {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 9px; padding: 7px 10px; min-height: 18px; }}
QComboBox:focus, QLineEdit:focus {{ border: 1px solid {c['accent']}; }}
QComboBox::drop-down {{ border: 0; width: 24px; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['line']}; selection-background-color: {c['sel']}; selection-color: {c['text']}; padding: 4px; outline: 0; }}
QListWidget {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 12px; padding: 4px; outline: 0; }}
QListWidget::item {{ border-bottom: 1px solid {c['line']}; }}
QListWidget::item:selected {{ background: {c['sel']}; border-radius: 8px; }}
QPlainTextEdit {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 10px; padding: 8px; }}
QPlainTextEdit:focus {{ border-color: {c['accent']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['line']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: none; }}
QRadioButton {{ spacing: 10px; padding: 6px 0; font-weight: 550; }}
QRadioButton::indicator {{ width: 18px; height: 18px; border-radius: 9px; border: 2px solid {c['muted']}; background: {c['surface']}; }}
QRadioButton::indicator:hover {{ border-color: {c['accent']}; }}
QRadioButton::indicator:checked {{ border: 2px solid {c['accent']}; background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 {c['accent']}, stop:0.55 {c['accent']}, stop:0.6 {c['surface']}, stop:1 {c['surface']}); }}
QRadioButton:disabled {{ color: {c['muted']}; }}
QPushButton#seg:checked {{ background: {c['accent']}; color: {c['accent_ink']}; border-color: {c['accent']}; }}
QProgressBar {{ background: {c['surface2']}; border: 0; border-radius: 3px; height: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}
QScrollArea {{ border: 0; background: transparent; }}
QListWidget#nav {{ background: {c['side']}; border: 0; border-right: 1px solid {c['line']}; padding: 16px 10px; outline: 0; }}
QListWidget#nav::item {{ padding: 9px 12px; border-radius: 9px; margin-bottom: 2px; color: {c['text']}; font-weight: 550; border: 0; }}
QListWidget#nav::item:hover {{ background: {c['surface2']}; }}
QListWidget#nav::item:selected {{ background: {c['sidesel']}; color: {c['text']}; font-weight: 650; }}
QCheckBox {{ spacing: 10px; padding: 4px 0; font-weight: 550; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {c['line']}; background: {c['surface']}; }}
QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; image: url({check}); }}
QSpinBox, QDoubleSpinBox {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 9px; padding: 6px 8px; min-width: 120px; }}
QTableWidget {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 10px; gridline-color: {c['line']}; selection-background-color: {c['sel']}; selection-color: {c['text']}; }}
QTableWidget QComboBox {{ border: 0; border-radius: 0; padding: 4px 8px; }}
QHeaderView::section {{ background: {c['surface2']}; border: 0; border-bottom: 1px solid {c['line']}; padding: 7px 8px; font-weight: 650; color: {c['muted']}; }}
QMenu {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 10px; padding: 5px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['sel']}; }}
QMenu::separator {{ height: 1px; background: {c['line']}; margin: 4px 6px; }}
#stepDot {{ background: {c['line']}; border-radius: 4px; }}
#stepDot[active="true"] {{ background: {c['accent']}; }}
/* legacy tiles (dialogs) */
#tile {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 14px; }}
#tileTitle {{ font-weight: 650; font-size: 13.5px; }}
#tileSub {{ color: {c['muted']}; font-size: 12px; }}
"""


def palette(c: dict) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(c["bg"]))
    p.setColor(QPalette.Base, QColor(c["surface"]))
    p.setColor(QPalette.Text, QColor(c["text"]))
    p.setColor(QPalette.WindowText, QColor(c["text"]))
    p.setColor(QPalette.Button, QColor(c["surface2"]))
    p.setColor(QPalette.ButtonText, QColor(c["text"]))
    p.setColor(QPalette.Highlight, QColor(c["accent"]))
    p.setColor(QPalette.HighlightedText, QColor(c["accent_ink"]))
    p.setColor(QPalette.PlaceholderText, QColor(c["muted"]))
    return p
