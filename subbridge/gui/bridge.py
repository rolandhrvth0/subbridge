from PySide6.QtCore import QObject, Signal


class Bridge(QObject):
    """Thread → GUI signal hub."""
    status = Signal(str, str, str)
    preview = Signal(object, object)
    subtitle = Signal(dict)
    stats = Signal(dict)
    clients = Signal(int, list)
    download = Signal(int, int)
    download_done = Signal(str)
    overlay = Signal(list)
    ocr_ready = Signal(str)
    phone = Signal(object)
    feed = Signal()
