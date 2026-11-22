"""Announces the server on the local network (mDNS / DNS-SD, service type _subbridge._tcp) so the
Android app finds the computer by itself. Optional: silently does nothing without `zeroconf`."""
from __future__ import annotations

import logging
import socket

from ..branding import APP_NAME, VERSION

log = logging.getLogger(__name__)
SERVICE = "_subbridge._tcp.local."


class Announcer:
    def __init__(self):
        self._zc = None
        self._info = None

    def start(self, ip: str, port: int, https: bool, pin_required: bool):
        self.stop()
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except ImportError:
            return
        host = socket.gethostname().split(".")[0] or "PC"
        try:
            self._info = ServiceInfo(
                SERVICE, f"{APP_NAME} on {host}.{SERVICE}", addresses=[socket.inet_aton(ip)], port=port,
                properties={"v": VERSION, "https": "1" if https else "0", "pin": "1" if pin_required else "0",
                            "host": host}, server=f"{host}-subbridge.local.")
            self._zc = Zeroconf(interfaces=[ip])
            self._zc.register_service(self._info, allow_name_change=True)
        except Exception as e:  # noqa: BLE001  (no multicast on this network: QR/PIN still work)
            log.info("mDNS announce failed: %s", e)
            self.stop()

    def stop(self):
        if self._zc:
            try:
                if self._info:
                    self._zc.unregister_service(self._info)
                self._zc.close()
            except Exception:  # noqa: BLE001
                pass
        self._zc = self._info = None
