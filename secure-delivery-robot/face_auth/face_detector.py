"""
Face LOCATION only - where are the faces in this frame?

Kept separate from encoding because detection is cheap and useful on its own:
the robot can tell "someone is standing here" before doing the expensive
recognition work.
"""
from __future__ import annotations

import logging
from typing import List, Tuple

import cv2
import numpy as np

from config import settings

log = logging.getLogger(__name__)

Box = Tuple[int, int, int, int]      # (top, right, bottom, left)


class FaceDetector:
    def __init__(self, backend: str = None):
        self.backend = backend or settings.FACE_BACKEND
        self._cascade = None
        if self.backend == "lbph":
            self._cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    def detect(self, frame: np.ndarray) -> List[Box]:
        """Boxes in FULL-frame coordinates."""
        if frame is None:
            return []
        s = settings.FACE_DOWNSCALE
        small = cv2.resize(frame, (0, 0), fx=s, fy=s)

        if self.backend == "face_recognition":
            import face_recognition
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            boxes = face_recognition.face_locations(
                rgb, model=settings.FACE_DETECTION_MODEL)
        else:
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            rects = self._cascade.detectMultiScale(gray, 1.15, 5, minSize=(30, 30))
            boxes = [(y, x + w, y + h, x) for (x, y, w, h) in rects]

        k = 1.0 / s
        return [(int(t * k), int(r * k), int(b * k), int(l * k))
                for (t, r, b, l) in boxes]

    @staticmethod
    def largest(boxes: List[Box]) -> Box | None:
        """The closest person - the one being served."""
        if not boxes:
            return None
        return max(boxes, key=lambda b: (b[2] - b[0]) * (b[1] - b[3]))

    @staticmethod
    def draw(frame, boxes: List[Box], colour=(0, 255, 0), label: str = None):
        for (t, r, b, l) in boxes:
            cv2.rectangle(frame, (l, t), (r, b), colour, 2)
            if label:
                cv2.putText(frame, label, (l, max(t - 8, 16)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)
        return frame
