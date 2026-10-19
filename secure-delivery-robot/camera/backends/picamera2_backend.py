"""
Picamera2 - Raspberry Pi CSI ribbon camera.

The picamera2 import is deferred so this file imports cleanly on your laptop.

On Raspberry Pi OS Bookworm picamera2 is an APT package. Your venv must be
created with --system-site-packages or it will not be visible.

Mode switching on picamera2 requires stop -> configure -> start. That takes
roughly 300-600 ms, which is why MODE_SWITCH_SETTLE_SECONDS exists.
"""
import logging
from typing import Optional

import numpy as np

from config import settings
from core.interfaces import CameraSource

log = logging.getLogger(__name__)


class PiCamera2Camera(CameraSource):
    def __init__(self):
        self.picam2 = None
        self._started = False

    def open(self) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as e:
            raise RuntimeError(
                "picamera2 unavailable. sudo apt install -y python3-picamera2 "
                "and create the venv with --system-site-packages."
            ) from e
        self.picam2 = Picamera2()
        m = settings.CAMERA_MODES[settings.DEFAULT_CAMERA_MODE]
        self.configure(m["width"], m["height"], m["fps"])
        log.info("Picamera2 opened")

    def configure(self, width: int, height: int, fps: int) -> None:
        if self.picam2 is None:
            return
        if self._started:
            self.picam2.stop()
            self._started = False
        cfg = self.picam2.create_preview_configuration(
            main={"size": (width, height), "format": "RGB888"},
            controls={"FrameDurationLimits": (int(1e6 / fps), int(1e6 / fps))},
        )
        self.picam2.configure(cfg)
        self.picam2.start()
        self._started = True
        log.info("Picamera2 configured %dx%d @ %d fps", width, height, fps)

    def read(self) -> Optional[np.ndarray]:
        if self.picam2 is None or not self._started:
            return None
        frame = self.picam2.capture_array()
        if settings.FLIP_HORIZONTAL:
            import cv2
            frame = cv2.flip(frame, 1)
        return frame

    def close(self) -> None:
        if self.picam2 is not None:
            if self._started:
                self.picam2.stop()
            self.picam2.close()
            self.picam2 = None
            self._started = False
            log.info("Picamera2 closed")
