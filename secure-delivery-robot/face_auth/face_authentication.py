"""
Recipient verification — the decision that opens the lock.

THE UNLOCK RULE, in plain terms. A frame authorises a person only if ALL of:

  1. confidence >= UNLOCK_CONFIDENCE_THRESHOLD   (your 50%)
  2. the best match beats the runner-up by AUTH_MIN_MARGIN
  3. that same person wins AUTH_REQUIRED_STREAK frames in a row
  4. liveness passes, if REQUIRE_LIVENESS is on

Why 2 and 3 exist. Threshold alone answers "is this person similar enough?"
It never asks "similar compared to whom?" With several people enrolled, a
generic-looking face can sit just above 0.50 against three of them at once —
the margin check rejects that as ambiguous rather than picking one. And any
single frame can get lucky through motion blur or an odd expression; a streak
over roughly a quarter-second cannot.

Neither guard makes the system stricter for the legitimate recipient, who
clears all four trivially. They cost you nothing and remove the two failure
modes most likely to embarrass you during a demo.

Run standalone:  python -m face_auth.face_authentication
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from config import settings
from core import display
from core.events import Event, bus
from face_auth.face_database import FaceDatabase
from face_auth.face_encoder import FaceEncoder

log = logging.getLogger(__name__)


@dataclass
class FrameResult:
    """One frame's verdict. Not an unlock decision on its own."""
    name: Optional[str] = None
    confidence: float = 0.0
    margin: float = 0.0
    passes_threshold: bool = False
    face_count: int = 0
    box: Optional[tuple] = None
    reason: str = "no face detected"

    @property
    def is_candidate(self) -> bool:
        return self.passes_threshold and self.name is not None


@dataclass
class AuthOutcome:
    """The final answer. authorised=True is what opens the solenoid."""
    authorised: bool
    name: Optional[str]
    confidence: float
    reason: str
    attempts: int = 0
    elapsed: float = 0.0
    frames_checked: int = 0
    liveness_passed: bool = True
    history: List[str] = field(default_factory=list)


class FaceAuthenticator:
    def __init__(self, database: FaceDatabase = None, encoder: FaceEncoder = None):
        self.db = database or FaceDatabase.load()
        self.encoder = encoder or FaceEncoder()
        self._streak_name: Optional[str] = None
        self._streak = 0
        self._frames = 0
        self.attempts = 0
        self._locked_until = 0.0

    # ───────────────────────────────────────── per frame
    def check_frame(self, frame: np.ndarray) -> FrameResult:
        self._frames += 1
        if self.db.is_empty:
            return FrameResult(reason="nobody enrolled")

        encodings, boxes = self.encoder.encode(frame)
        if not encodings:
            return FrameResult(reason="no face detected")

        # Serve the closest face if several people are in shot.
        idx = int(np.argmax([(b[2] - b[0]) * (b[1] - b[3]) for b in boxes]))
        probe, box = encodings[idx], boxes[idx]

        known, names = self.db.flat()
        dists = self.encoder.distances(known, probe)
        if dists.size == 0:
            return FrameResult(face_count=len(boxes), box=box, reason="no encodings")

        order = np.argsort(dists)
        best_i = int(order[0])
        best_name = names[best_i]
        best_conf = self.encoder.confidence(float(dists[best_i]))

        # Runner-up must be a DIFFERENT person for the margin to mean anything.
        rival_conf = 0.0
        for j in order[1:]:
            if names[int(j)] != best_name:
                rival_conf = self.encoder.confidence(float(dists[int(j)]))
                break
        margin = best_conf - rival_conf

        if best_conf < settings.UNLOCK_CONFIDENCE_THRESHOLD:
            reason = (f"below threshold "
                      f"({best_conf:.0%} < {settings.UNLOCK_CONFIDENCE_THRESHOLD:.0%})")
            return FrameResult(None, best_conf, margin, False,
                               len(boxes), box, reason)

        if margin < settings.AUTH_MIN_MARGIN:
            return FrameResult(None, best_conf, margin, False, len(boxes), box,
                               f"ambiguous (margin {margin:.2f})")

        return FrameResult(best_name, best_conf, margin, True,
                           len(boxes), box, "candidate")

    # ───────────────────────────────────────── streak
    def update_streak(self, r: FrameResult) -> Optional[str]:
        """Feed frames in; returns a name once the streak requirement is met."""
        if r.is_candidate and r.name == self._streak_name:
            self._streak += 1
        elif r.is_candidate:
            self._streak_name, self._streak = r.name, 1
        else:
            self._streak_name, self._streak = None, 0
        return (self._streak_name
                if self._streak >= settings.AUTH_REQUIRED_STREAK else None)

    @property
    def streak_progress(self) -> tuple:
        return (self._streak, settings.AUTH_REQUIRED_STREAK)

    def reset(self) -> None:
        self._streak_name, self._streak, self._frames = None, 0, 0

    # ───────────────────────────────────────── full attempt
    def authenticate(self, camera, on_frame=None) -> AuthOutcome:
        """
        Blocking verification loop. `camera` is a CameraManager ALREADY in
        FACE_AUTH mode — this method does not switch modes itself, because
        main.py owns that transition.
        """
        if time.time() < self._locked_until:
            wait = self._locked_until - time.time()
            return AuthOutcome(False, None, 0.0,
                               f"locked out for {wait:.0f}s more")

        self.reset()
        self.attempts += 1
        bus.emit(Event.AUTH_STARTED, attempt=self.attempts)

        start = time.time()
        deadline = start + settings.AUTH_TIMEOUT_SECONDS
        history, last = [], FrameResult()

        liveness = None
        if settings.REQUIRE_LIVENESS:
            from face_auth.liveness import LivenessChecker
            liveness = LivenessChecker()

        while time.time() < deadline:
            frame = camera.read()
            if frame is None:
                time.sleep(0.02)
                continue

            last = self.check_frame(frame)
            history.append(last.reason)
            bus.emit(Event.AUTH_FRAME, result=last)
            if on_frame:
                on_frame(frame, last, self.streak_progress)

            if liveness is not None and last.box:
                liveness.update(frame, last.box)

            confirmed = self.update_streak(last)
            if confirmed:
                if liveness is not None and not liveness.passed:
                    continue          # keep looping until they blink
                outcome = AuthOutcome(
                    True, confirmed, last.confidence, "authorised",
                    self.attempts, time.time() - start, self._frames,
                    liveness.passed if liveness else True, history[-8:])
                log.info("AUTHORISED %s at %.0f%% confidence (margin %.2f) "
                         "after %d frames",
                         confirmed, last.confidence * 100, last.margin,
                         self._frames)
                bus.emit(Event.AUTH_SUCCESS, name=confirmed,
                         confidence=last.confidence)
                return outcome

        reason = ("timeout - " + last.reason) if last.reason else "timeout"
        log.warning("Authentication failed: %s", reason)
        bus.emit(Event.AUTH_FAILED, reason=reason, attempt=self.attempts)

        if self.attempts >= settings.AUTH_MAX_ATTEMPTS:
            self._locked_until = time.time() + settings.AUTH_LOCKOUT_SECONDS
            log.error("Max attempts reached - locked out for %ds",
                      settings.AUTH_LOCKOUT_SECONDS)

        return AuthOutcome(False, None, last.confidence, reason,
                           self.attempts, time.time() - start, self._frames,
                           False, history[-8:])


def main() -> int:
    import cv2
    from camera import CameraManager, CameraMode
    from core.logging_setup import setup_logging
    setup_logging()

    auth = FaceAuthenticator()
    if auth.db.is_empty:
        print("Nobody enrolled. Run:\n"
              "  python -m face_auth.face_registration --name 'Your Name'")
        return 1

    print(f"Enrolled: {auth.db.summary()}")
    print(f"Threshold {settings.UNLOCK_CONFIDENCE_THRESHOLD:.0%} | "
          f"streak {settings.AUTH_REQUIRED_STREAK} | "
          f"margin {settings.AUTH_MIN_MARGIN}\n'q' quits.\n")

    with CameraManager() as cam:
        cam.set_mode(CameraMode.FACE_AUTH)     # same switch main.py performs
        while True:
            frame = cam.read()
            if frame is None:
                continue
            r = auth.check_frame(frame)
            confirmed = auth.update_streak(r)
            done, need = auth.streak_progress

            colour = ((0, 200, 0) if confirmed else
                      (0, 200, 200) if r.is_candidate else (0, 0, 255))
            if r.box:
                t, rt, b, l = r.box
                cv2.rectangle(frame, (l, t), (rt, b), colour, 2)
            cv2.putText(frame, f"{r.name or 'UNKNOWN'}  {r.confidence:.0%}  "
                               f"margin {r.margin:+.2f}  [{done}/{need}]",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2)
            cv2.putText(frame, "UNLOCK" if confirmed else r.reason,
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)
            display.show("Face authentication", frame)
            if display.wait_key(1) == ord("q"):
                break
    display.destroy_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
