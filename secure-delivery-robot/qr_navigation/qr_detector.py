"""
QR marker detection.

This module ONLY finds QR codes in a frame and decodes their text. It knows
nothing about MARKER 1..5 / STOP or what they mean - that mapping lives in
qr_commands.py, and the confirmation/locking behaviour lives in
marker_handler.py. Keeping this file dumb-and-simple means the detection
backend (OpenCV vs pyzbar, laptop webcam vs Pi camera) can change without
touching any navigation logic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np

from core import display
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class QRDetection:
    data: str
    points: np.ndarray
    center: tuple
    area: float


class QRDetector:
    def __init__(self, backend: str = None):
        self.backend = backend or settings.QR_BACKEND
        self._cv = cv2.QRCodeDetector() if self.backend == "opencv" else None
        if self.backend == "pyzbar":
            from pyzbar import pyzbar  # noqa: F401

    def detect(self, frame: Optional[np.ndarray]) -> List[QRDetection]:
        if frame is None:
            return []
        return (self._opencv(frame) if self.backend == "opencv"
                else self._pyzbar(frame))

    def _opencv(self, frame):
        try:
            ok, texts, pts, _ = self._cv.detectAndDecodeMulti(frame)
        except cv2.error:
            return []
        if not ok or pts is None:
            return []
        out = []
        for text, quad in zip(texts, pts):
            if text:
                d = self._make(text, quad.astype(np.float32))
                if d:
                    out.append(d)
        return out

    def _pyzbar(self, frame):
        from pyzbar import pyzbar
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        out = []
        for s in pyzbar.decode(gray, symbols=[pyzbar.ZBarSymbol.QRCODE]):
            quad = np.array([[p.x, p.y] for p in s.polygon], dtype=np.float32)
            d = self._make(s.data.decode("utf-8", "replace"), quad)
            if d:
                out.append(d)
        return out

    @staticmethod
    def _make(text, quad):
        if quad is None or len(quad) < 3:
            return None
        area = float(cv2.contourArea(quad))
        if area < settings.QR_MIN_AREA:
            return None
        return QRDetection(text.strip(), quad,
                           (float(quad[:, 0].mean()), float(quad[:, 1].mean())),
                           area)

    @staticmethod
    def nearest(dets):
        """The most prominent (largest, i.e. closest) QR code in view, if any."""
        return max(dets, key=lambda d: d.area) if dets else None

    @staticmethod
    def draw(frame, dets):
        for d in dets:
            cv2.polylines(frame, [d.points.astype(int)], True, (0, 255, 0), 2)
            x, y = d.points.astype(int)[0]
            cv2.putText(frame, d.data, (x, max(y - 10, 18)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
            cv2.circle(frame, (int(d.center[0]), int(d.center[1])), 4,
                       (0, 255, 0), -1)
        return frame


def main():
    from core.logging_setup import setup_logging
    setup_logging()
    from camera import CameraManager
    det = QRDetector()
    print(f"Backend: {det.backend}. Show a QR code. 'q' quits.")
    with CameraManager() as cam:
        while True:
            frame = cam.read()
            if frame is None:
                continue
            found = det.detect(frame)
            for d in found:
                print(f"  {d.data:<12} area={d.area:7.0f}")
            if not settings.HEADLESS:
                display.show("QR detector", QRDetector.draw(frame, found))
                if display.wait_key(1) == ord("q"):
                    break
    display.destroy_all()


if __name__ == "__main__":
    main()
