"""
Marker Handler - stability, 5-second confirmation, and duplicate-locking.

This is the piece that gives you "real-world-style" QR confirmation instead
of reacting the instant a code is decoded once:

    seen once                         -> not enough, ignored
    seen QR_STABLE_FRAMES in a row     -> stable: start the confirmation timer
    stays visible QR_CONFIRMATION_TIME seconds (default 5) -> CONFIRMED
    stays visible after that           -> LOCKED: ignored, command not repeated
    missing QR_LOST_FRAMES frames in a row -> RESET: can be confirmed again
    a DIFFERENT marker appears         -> gets its own, independent attempt

Only one marker is tracked at a time (the camera only ever really sees one
QR code at a time in front of the robot), but different markers are fully
independent of each other: MARKER 2 being locked does not block MARKER 4
from starting its own confirmation the moment it appears.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class MarkerStatus:
    """A snapshot returned by every update() call, mainly for on-screen UI."""
    tracked: Optional[str] = None      # raw QR payload currently being watched
    stable_frames: int = 0
    confirming: bool = False           # timer running, not yet at 5s
    elapsed: float = 0.0               # seconds into the confirmation timer
    locked: bool = False               # already confirmed & still visible
    just_confirmed: Optional[str] = None   # set for exactly ONE update() call


class MarkerHandler:
    def __init__(self):
        self._tracked: Optional[str] = None
        self._stable_frames: int = 0
        self._confirm_start: Optional[float] = None
        self._locked: bool = False
        self._lost_frames: int = 0

    def update(self, raw_marker: Optional[str]) -> MarkerStatus:
        """Call once per camera frame with the currently-visible QR payload
        (or None if no QR is visible this frame)."""
        now = time.time()

        # ── same marker still visible ────────────────────────────────
        if raw_marker is not None and raw_marker == self._tracked:
            self._lost_frames = 0

            if self._locked:
                # Already confirmed once. Ignore it while it stays in view.
                return MarkerStatus(self._tracked, self._stable_frames,
                                     False, 0.0, True, None)

            self._stable_frames += 1
            if self._stable_frames < settings.QR_STABLE_FRAMES:
                return MarkerStatus(self._tracked, self._stable_frames,
                                     False, 0.0, False, None)

            if self._confirm_start is None:
                self._confirm_start = now
                logger.info("QR '%s' stable - starting %ss confirmation",
                           self._tracked, settings.QR_CONFIRMATION_TIME)

            elapsed = now - self._confirm_start
            if elapsed >= settings.QR_CONFIRMATION_TIME:
                self._locked = True
                logger.info("QR '%s' CONFIRMED after %.1fs",
                           self._tracked, elapsed)
                return MarkerStatus(self._tracked, self._stable_frames,
                                     False, elapsed, True, self._tracked)

            return MarkerStatus(self._tracked, self._stable_frames,
                                 True, elapsed, False, None)

        # ── nothing visible this frame ───────────────────────────────
        if raw_marker is None:
            if self._tracked is None:
                return MarkerStatus()
            self._lost_frames += 1
            if self._lost_frames >= settings.QR_LOST_FRAMES:
                logger.debug("QR '%s' lost for %d frames - resetting",
                             self._tracked, self._lost_frames)
                lost_id = self._tracked
                self._reset()
                logger.debug("Handler reset; '%s' can be confirmed again",
                             lost_id)
                return MarkerStatus()
            return MarkerStatus(
                self._tracked, self._stable_frames,
                self._confirm_start is not None,
                (now - self._confirm_start) if self._confirm_start else 0.0,
                self._locked, None)

        # ── a DIFFERENT marker just appeared - starts its own attempt ──
        logger.debug("New marker '%s' seen (was tracking %r)",
                     raw_marker, self._tracked)
        self._reset()
        self._tracked = raw_marker
        self._stable_frames = 1
        return MarkerStatus(self._tracked, 1, False, 0.0, False, None)

    def _reset(self) -> None:
        self._tracked = None
        self._stable_frames = 0
        self._confirm_start = None
        self._locked = False
        self._lost_frames = 0

    def reset(self) -> None:
        """Public reset, e.g. when the mission restarts."""
        self._reset()
