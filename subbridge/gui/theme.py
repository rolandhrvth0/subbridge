from PySide6.QtGui import QColor, QPalette

LIGHT = dict(bg="#f4f5f7", surface="#ffffff", surface2="#eef0f3", line="#e1e4e9", text="#16191e",
             muted="#69717f", accent="#c98a12", accent_hover="#b47a0c", accent_ink="#ffffff",
             ok="#1f9d5c", warn="#b7791f", danger="#d64545", sel="#fff4dc")
DARK = dict(bg="#111317", surface="#191c21", surface2="#22262d", line="#2c313a", text="#eceef2",
            muted="#8d95a4", accent="#f5b83d", accent_hover="#ffc75a", accent_ink="#1a1405",
            ok="#4ccf8a", warn="#f5b83d", danger="#ff6b6b", sel="#3a2f17")


def stylesheet(c: dict) -> str:
    from ..paths import resource_dir
    check = (resource_dir() / "assets" / "ui" / f"check-{c['accent_ink'].lstrip('#')}.svg").as_posix()
    return f"""
* {{ font-family: "Inter Variable", "Inter", "Segoe UI", sans-serif; font-size: 13.5px; color: {c['text']}; }}
QMainWindow, QDialog, #root {{ background: {c['bg']}; }}
QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['line']}; padding: 6px 8px; border-radius: 6px; }}
#card {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 12px; }}
#cardTitle {{ font-size: 14.5px; font-weight: 650; }}
#h1 {{ font-size: 22px; font-weight: 700; }}
#h2 {{ font-size: 16px; font-weight: 650; }}
#brand {{ font-size: 16px; font-weight: 700; }}
#muted, QLabel[muted="true"] {{ color: {c['muted']}; }}
#small {{ color: {c['muted']}; font-size: 12px; }}
#pin {{ font-size: 28px; font-weight: 700; letter-spacing: 6px; }}
#subHu {{ font-size: 17px; font-weight: 600; }}
#subEn {{ color: {c['muted']}; font-size: 13px; }}
#speaker {{ color: {c['accent']}; font-weight: 650; font-size: 12px; }}
#preview {{ background: {c['surface2']}; border-radius: 8px; color: {c['muted']}; }}
#statusPill {{ border-radius: 13px; padding: 4px 12px; font-weight: 600; font-size: 12.5px; background: {c['surface2']}; color: {c['muted']}; }}
#statusPill[state="running"] {{ background: {c['ok']}22; color: {c['ok']}; }}
#statusPill[state="waiting"] {{ background: {c['warn']}26; color: {c['warn']}; }}
#statusPill[state="error"] {{ background: {c['danger']}22; color: {c['danger']}; }}
#alert {{ background: {c['warn']}1c; border: 1px solid {c['warn']}55; border-radius: 10px; }}
#alertText {{ color: {c['text']}; }}
QPushButton {{ background: {c['surface2']}; border: 1px solid {c['line']}; border-radius: 9px; padding: 8px 14px; font-weight: 600; }}
QPushButton:hover {{ border-color: {c['muted']}; }}
QPushButton:pressed {{ background: {c['line']}; }}
QPushButton:disabled {{ color: {c['muted']}; }}
QPushButton#primary {{ background: {c['accent']}; color: {c['accent_ink']}; border: 0; padding: 10px 20px; font-size: 14.5px; }}
QPushButton#primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#danger {{ background: {c['danger']}; color: #fff; border: 0; padding: 10px 20px; font-size: 14.5px; }}
QPushButton#ghost, QToolButton {{ background: transparent; border: 0; border-radius: 8px; padding: 6px; }}
QPushButton#ghost:hover, QToolButton:hover {{ background: {c['surface2']}; }}
QComboBox, QLineEdit, QSpinBox {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 8px; padding: 7px 10px; min-height: 18px; }}
QComboBox:focus, QLineEdit:focus {{ border-color: {c['accent']}; }}
QComboBox::drop-down {{ border: 0; width: 24px; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['line']}; selection-background-color: {c['sel']}; selection-color: {c['text']}; padding: 4px; outline: 0; }}
QRadioButton {{ spacing: 10px; padding: 6px 0; }}
QProgressBar {{ background: {c['surface2']}; border: 0; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
QScrollArea {{ border: 0; background: transparent; }}
QListWidget#nav {{ background: {c['surface']}; border: 0; border-right: 1px solid {c['line']}; padding: 16px 10px; outline: 0; }}
QListWidget#nav::item {{ padding: 10px 12px; border-radius: 8px; margin-bottom: 2px; color: {c['muted']}; font-weight: 600; }}
QListWidget#nav::item:hover {{ background: {c['surface2']}; color: {c['text']}; }}
QListWidget#nav::item:selected {{ background: {c['sel']}; color: {c['text']}; }}
QCheckBox {{ spacing: 10px; padding: 4px 0; font-weight: 550; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {c['line']}; background: {c['surface']}; }}
QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; image: url({check}); }}
QSpinBox, QDoubleSpinBox {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 8px; padding: 6px 8px; min-width: 120px; }}
QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {c['accent']}; }}
QTableWidget {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 8px; gridline-color: {c['line']}; selection-background-color: {c['sel']}; selection-color: {c['text']}; }}
QTableWidget QComboBox {{ border: 0; border-radius: 0; padding: 4px 8px; }}
QHeaderView::section {{ background: {c['surface2']}; border: 0; border-bottom: 1px solid {c['line']}; padding: 7px 8px; font-weight: 650; color: {c['muted']}; }}
QMenu {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 8px; padding: 5px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['sel']}; }}
QMenu::separator {{ height: 1px; background: {c['line']}; margin: 4px 6px; }}
#tile {{ background: {c['surface']}; border: 1px solid {c['line']}; border-radius: 12px; }}
#tile:hover {{ border-color: {c['muted']}; }}
#tile[state="on"] {{ border: 1px solid {c['accent']}; background: {c['sel']}; }}
#tile[state="disabled"] {{ background: {c['bg']}; }}
#tile[state="disabled"] #tileTitle {{ color: {c['muted']}; }}
#tileIcon {{ background: {c['surface2']}; border-radius: 9px; }}
#tile[state="on"] #tileIcon {{ background: {c['accent']}; }}
#tileTitle {{ font-weight: 650; font-size: 13.5px; }}
#tileSub {{ color: {c['muted']}; font-size: 12px; }}
#stepDot {{ background: {c['line']}; border-radius: 4px; }}
#stepDot[active="true"] {{ background: {c['accent']}; }}
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
