"""
Turns a face into a comparable vector, and compares vectors.

Two backends behind one interface:
  face_recognition  - dlib, 128-d embedding, accurate. No ARM wheel: on the
                      Pi it compiles from source (45-90 min). See SETUP.md.
  lbph              - OpenCV only, installs instantly, much faster, clearly
                      less accurate. Set FACE_BACKEND="lbph" to use it.

Both expose encode() and confidence(), so nothing downstream cares.
"""
from __future__ import annotations

import logging
from typing import List, Tuple

import cv2
import numpy as np

from config import settings
from face_auth.face_detector import Box, FaceDetector

log = logging.getLogger(__name__)


class FaceEncoder:
    def __init__(self, backend: str = None):
        self.backend = backend or settings.FACE_BACKEND
        self.detector = FaceDetector(self.backend)

        if self.backend == "face_recognition":
            try:
                import face_recognition  # noqa: F401
            except ImportError as e:
                raise RuntimeError(
                    "face_recognition not installed.\n"
                    "  Laptop: pip install face_recognition\n"
                    "  Pi 4  : see SETUP.md (dlib compiles from source)\n"
                    "  Or set FACE_BACKEND='lbph' in config/settings.py"
                ) from e
        elif self.backend == "lbph":
            if not hasattr(cv2, "face"):
                log.warning("opencv-contrib not installed; using raw pixel "
                            "vectors. Accuracy will be poor.")
        else:
            raise ValueError(f"Unknown FACE_BACKEND: {self.backend!r}")

    # ────────────────────────────────────────────────────────
    def encode(self, frame: np.ndarray) -> Tuple[List[np.ndarray], List[Box]]:
        if frame is None:
            return [], []
        s = settings.FACE_DOWNSCALE
        small = cv2.resize(frame, (0, 0), fx=s, fy=s)

        if self.backend == "face_recognition":
            import face_recognition
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            small_boxes = face_recognition.face_locations(
                rgb, model=settings.FACE_DETECTION_MODEL)
            encodings = face_recognition.face_encodings(rgb, small_boxes)
        else:
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            rects = cascade.detectMultiScale(gray, 1.15, 5, minSize=(30, 30))
            small_boxes, encodings = [], []
            for (x, y, w, h) in rects:
                small_boxes.append((y, x + w, y + h, x))
                chip = cv2.resize(gray[y:y + h, x:x + w], (100, 100))
                encodings.append(
                    cv2.equalizeHist(chip).astype(np.float32).ravel() / 255.0)

        k = 1.0 / s
        boxes = [(int(t * k), int(r * k), int(b * k), int(l * k))
                 for (t, r, b, l) in small_boxes]
        return encodings, boxes

    # ────────────────────────────────────────────────────────
    def distances(self, known: List[np.ndarray], probe: np.ndarray) -> np.ndarray:
        if not known:
            return np.array([])
        if self.backend == "face_recognition":
            import face_recognition
            return face_recognition.face_distance(known, probe)
        stack = np.vstack(known)
        return np.linalg.norm(stack - probe, axis=1) / np.sqrt(stack.shape[1])

    @staticmethod
    def confidence(distance: float) -> float:
        """
        Map encoding distance -> a 0.0-1.0 confidence the UI and the unlock
        rule both use.

        For dlib embeddings, distance ~0.0 is the same photo, ~0.6 is the
        library's default "probably same person" line, and >0.8 is clearly a
        different person. This maps 0.0 -> 1.0 and 1.0 -> 0.0, so your
        UNLOCK_CONFIDENCE_THRESHOLD of 0.50 corresponds to a distance of 0.50.
        """
        return float(max(0.0, min(1.0, 1.0 - distance)))
