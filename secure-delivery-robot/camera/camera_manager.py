"""
CameraManager - one camera, several task-specific modes.

THIS IS THE MODE SWITCHING YOU ASKED FOR.

While navigating, the camera runs 640x480 @ 30fps: wide and fast, because QR
markers are large and the robot is moving. The moment the destination marker
fires ARRIVE, main.py calls:

    camera.set_mode(CameraMode.FACE_AUTH)

and the same physical camera reconfigures to 1280x720 @ 15fps. Face encoding
needs pixels on the face, not frame rate — the robot is stationary by then.

Two details that matter in practice:

1. A reconfigure is not instantaneous. On picamera2 it is a genuine
   stop/configure/start cycle (~300-600 ms) and auto-exposure plus white
   balance need time to re-converge afterwards. Frames captured during that
   window are often dark or washed out, and will wreck your first few face
   encodings. MODE_SWITCH_SETTLE_SECONDS drains them before handing control
   back. Do not set it to zero.

2. set_mode() is idempotent. Calling it every loop iteration is harmless —
   it returns immediately if the mode already matches.
"""
from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

import numpy as np

from config import settings
from core.events import Event, bus
from core.interfaces import CameraSource

log = logging.getLogger(__name__)


class CameraMode(str, Enum):
    NAVIGATION = "NAVIGATION"
    FACE_AUTH = "FACE_AUTH"
    IDLE = "IDLE"


def _build_backend() -> CameraSource:
    backend = settings.CAMERA_BACKEND
    if backend == "webcam":
        from camera.backends.webcam import WebcamCamera
        return WebcamCamera()
    if backend == "picamera2":
        from camera.backends.picamera2_backend import PiCamera2Camera
        return PiCamera2Camera()
    raise ValueError(f"Unknown CAMERA_BACKEND: {backend!r}")


class CameraManager:
    def __init__(self, source: CameraSource = None):
        self.source = source or _build_backend()
        self._mode: Optional[CameraMode] = None
        self._is_open = False
        self.switch_count = 0

    # ───────────────────────────────────────────── lifecycle
    def open(self, mode: CameraMode = None) -> "CameraManager":
        if not self._is_open:
            self.source.open()
            self._is_open = True
        self.set_mode(mode or CameraMode(settings.DEFAULT_CAMERA_MODE),
                      settle=False)
        return self

    def close(self) -> None:
        if self._is_open:
            self.source.close()
            self._is_open = False
            self._mode = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()
        return False

    # ───────────────────────────────────────────── modes
    @property
    def mode(self) -> Optional[CameraMode]:
        return self._mode

    def set_mode(self, mode: CameraMode, settle: bool = True) -> bool:
        """Reconfigure for a task. Returns True if a switch actually happened."""
        mode = CameraMode(mode)
        if mode is self._mode:
            return False

        spec = settings.CAMERA_MODES[mode.value]
        previous = self._mode
        t0 = time.time()

        self.source.configure(spec["width"], spec["height"], spec["fps"])
        if settle:
            self._drain(settings.MODE_SWITCH_SETTLE_SECONDS)

        self._mode = mode
        self.switch_count += 1
        log.info("Camera mode %s -> %s (%dx%d @ %dfps) in %.0f ms",
                 previous.value if previous else "none", mode.value,
                 spec["width"], spec["height"], spec["fps"],
                 (time.time() - t0) * 1000)
        bus.emit(Event.MODE_CHANGED, previous=previous, current=mode,
                 spec=spec)
        return True

    def _drain(self, seconds: float) -> int:
        """Throw away frames while exposure and white balance re-converge."""
        end, n = time.time() + seconds, 0
        while time.time() < end:
            if self.source.read() is not None:
                n += 1
        log.debug("Drained %d settling frames", n)
        return n

    # Convenience wrappers so call sites read like English.
    def navigation_mode(self) -> bool:
        return self.set_mode(CameraMode.NAVIGATION)

    def face_auth_mode(self) -> bool:
        return self.set_mode(CameraMode.FACE_AUTH)

    def idle_mode(self) -> bool:
        return self.set_mode(CameraMode.IDLE)

    # ───────────────────────────────────────────── frames
    def read(self) -> Optional[np.ndarray]:
        if not self._is_open:
            return None
        return self.source.read()

    def read_or_raise(self) -> np.ndarray:
        frame = self.read()
        if frame is None:
            raise RuntimeError("Camera returned no frame")
        return frame

    @property
    def resolution(self) -> tuple:
        if self._mode is None:
            return (0, 0)
        s = settings.CAMERA_MODES[self._mode.value]
        return (s["width"], s["height"])
