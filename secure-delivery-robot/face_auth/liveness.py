"""
FUTURE SCOPE - anti-spoofing.

The honest limitation of this project: a printed photo of the recipient, held
in front of the camera, unlocks the compartment. Every threshold guard in
face_authentication.py is defeated by it, because a photo genuinely IS the
right face.

Blink detection is the cheapest real defence. A photo does not blink.

The implementation below is a working motion-based approximation: it tracks
how much the eye region of the detected face changes over time and calls it
live if the variance crosses a threshold. It catches a static printout. It
does NOT catch a video replay on a phone screen.

The proper version uses eye aspect ratio from facial landmarks
(face_recognition.face_landmarks gives you left_eye / right_eye point lists).
That is a good final-year extension: compute EAR per frame, watch for the
characteristic dip-and-recover of a blink.

Enable with REQUIRE_LIVENESS=True in settings once you implement it properly.
"""
from __future__ import annotations

import logging
from collections import deque

import cv2
import numpy as np

log = logging.getLogger(__name__)


class LivenessChecker:
    MOTION_THRESHOLD = 6.0
    WINDOW = 12

    def __init__(self):
        self._history = deque(maxlen=self.WINDOW)
        self.passed = False

    def update(self, frame: np.ndarray, box) -> bool:
        """Feed each authentication frame plus the face box."""
        t, r, b, l = box
        h = b - t
        eye_band = frame[t + int(h * 0.20): t + int(h * 0.50), l:r]
        if eye_band.size == 0:
            return self.passed

        gray = cv2.cvtColor(eye_band, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (64, 24)).astype(np.float32)
        self._history.append(gray)

        if len(self._history) >= self.WINDOW:
            stack = np.stack(self._history)
            motion = float(np.mean(np.std(stack, axis=0)))
            if motion > self.MOTION_THRESHOLD:
                if not self.passed:
                    log.info("Liveness passed (motion %.1f)", motion)
                self.passed = True
        return self.passed

    def reset(self) -> None:
        self._history.clear()
        self.passed = False
