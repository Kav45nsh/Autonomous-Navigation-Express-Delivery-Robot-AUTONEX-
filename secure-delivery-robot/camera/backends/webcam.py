
"""OpenCV VideoCapture - laptop built-in or USB webcam."""

import logging
from typing import Optional

import cv2
import numpy as np

from config import settings
from core.interfaces import CameraSource

log = logging.getLogger(__name__)


class WebcamCamera(CameraSource):
    def __init__(self, index: int = None):
        self.index = settings.CAMERA_INDEX if index is None else index
        self.cap: Optional[cv2.VideoCapture] = None

    def open(self) -> None:
        self._open_camera()

    def _open_camera(self) -> None:
        self.cap = cv2.VideoCapture(self.index)

        if not self.cap.isOpened():
            self.cap.release()
            self.cap = None
            raise RuntimeError(
                f"Cannot open webcam index {self.index}. Try CAMERA_INDEX=1, "
                "close other apps using the camera, check OS permissions."
            )

        log.info("Webcam opened (index %s)", self.index)

    def configure(self, width: int, height: int, fps: int) -> None:
        if self.cap is None:
            return

        # Windows webcams can become unstable when resolution/FPS is changed
        # on an already-running VideoCapture. Reopen the camera instead.
        log.debug(
            "Reconfiguring webcam to %dx%d @ %dfps",
            width,
            height,
            fps,
        )

        self.cap.release()
        self.cap = None

        # Give the Windows camera driver a moment to release the device.
        import time
        time.sleep(0.2)

        self._open_camera()

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)

        got = (
            int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )

        if got != (width, height):
            log.warning(
                "Webcam refused %dx%d, gave %dx%d (driver limitation)",
                width,
                height,
                *got,
            )

    def read(self) -> Optional[np.ndarray]:
        if self.cap is None:
            return None

        try:
            ok, frame = self.cap.read()
        except cv2.error as exc:
            log.warning("Webcam read failed: %s", exc)
            return None

        if not ok or frame is None:
            return None

        return cv2.flip(frame, 1) if settings.FLIP_HORIZONTAL else frame

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            log.info("Webcam released")
