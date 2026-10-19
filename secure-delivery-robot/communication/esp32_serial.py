"""
Serial link to an ESP32 co-processor.

FUTURE SCOPE, and a genuinely good architectural move. Offloading motor PWM
and sensor polling to an ESP32 gives you hard real-time timing that Linux
cannot promise, frees the Pi to do vision work, and means a Python crash
cannot leave the motors running.

Disabled by default (ESP32_ENABLED=False). The rest of the project works
without it; turn it on when the hardware exists.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from communication import protocol
from config import settings
from core.interfaces import Transport

log = logging.getLogger(__name__)


class ESP32Serial(Transport):
    def __init__(self, port: str = None, baud: int = None):
        self.port = port or settings.ESP32_PORT
        self.baud = baud or settings.ESP32_BAUD
        self._serial = None
        self._rx_thread: Optional[threading.Thread] = None
        self._running = False
        self.on_event: Optional[Callable[[protocol.Message], None]] = None
        self.last_seen = 0.0

    # ───────────────────────────────────── transport
    def connect(self) -> None:
        try:
            import serial
        except ImportError as e:
            raise RuntimeError("pyserial missing. pip install pyserial") from e
        self._serial = serial.Serial(self.port, self.baud,
                                     timeout=settings.ESP32_TIMEOUT)
        time.sleep(2.0)                 # ESP32 resets when the port opens
        self._running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()
        log.info("ESP32 connected on %s @ %d", self.port, self.baud)

    def send(self, line: str) -> None:
        if self._serial is None:
            log.debug("ESP32 not connected, dropping: %s", line)
            return
        self._serial.write((line + "\n").encode("utf-8"))

    def send_message(self, msg: protocol.Message) -> None:
        self.send(msg.encode())

    def receive(self) -> Optional[str]:
        if self._serial is None:
            return None
        raw = self._serial.readline()
        return raw.decode("utf-8", "replace").strip() or None

    def close(self) -> None:
        self._running = False
        if self._serial is not None:
            try:
                self.send_message(protocol.stop())
                self._serial.close()
            except Exception:
                pass
            self._serial = None
            log.info("ESP32 disconnected")

    # ───────────────────────────────────── rx
    def _rx_loop(self) -> None:
        while self._running:
            try:
                line = self.receive()
            except Exception:
                log.exception("ESP32 read error")
                break
            if not line:
                continue
            msg = protocol.Message.decode(line)
            if msg is None:
                log.warning("Bad/corrupt frame from ESP32: %r", line)
                continue
            self.last_seen = time.time()
            if self.on_event:
                self.on_event(msg)

    @property
    def is_alive(self) -> bool:
        return (self._serial is not None and
                time.time() - self.last_seen < settings.ESP32_HEARTBEAT_SECONDS * 3)


class NullTransport(Transport):
    """Used when ESP32_ENABLED is False. Everything downstream still works."""

    def connect(self) -> None: pass
    def send(self, line: str) -> None: pass
    def receive(self) -> Optional[str]: return None
    def close(self) -> None: pass


def build_transport() -> Transport:
    return ESP32Serial() if settings.ESP32_ENABLED else NullTransport()
