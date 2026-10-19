"""
SolenoidLock - the timed unlock policy wrapped around a raw LockDevice.

The backends below only know energise/release. This class owns the question
"how long should it stay open, and who guarantees it closes again?"

    lock = SolenoidLock()
    lock.unlock(reason="face match", recipient="Priya")   # opens, auto-relocks
    lock.wait_until_locked()

Fail-secure: the relock is scheduled on a daemon timer AND enforced by
context-manager exit AND by atexit in the GPIO backend. Three independent
paths, because a compartment stuck open is the worst outcome this project has.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from config import settings
from core.events import Event, bus
from core.interfaces import LockDevice

log = logging.getLogger(__name__)


def build_lock_device() -> LockDevice:
    if settings.LOCK_BACKEND == "gpio":
        from security.lock_backends.gpio_lock import GPIOSolenoidLock
        return GPIOSolenoidLock()
    from security.lock_backends.simulated_lock import SimulatedLock
    return SimulatedLock()


class SolenoidLock:
    def __init__(self, device: LockDevice = None):
        self.device = device or build_lock_device()
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self.unlock_count = 0
        self.last_reason: Optional[str] = None
        self.last_recipient: Optional[str] = None

    # ───────────────────────────────────────────────────────
    @property
    def is_unlocked(self) -> bool:
        return self.device.is_unlocked

    def unlock(self, duration: float = None, reason: str = "authorised",
               recipient: str = None) -> bool:
        """Open for `duration` seconds, then relock automatically."""
        duration = settings.UNLOCK_DURATION_SECONDS if duration is None else duration
        duration = min(duration, settings.MAX_CONTINUOUS_ENERGISE_S)

        with self._lock:
            if self.device.is_unlocked:
                log.warning("Already unlocked - ignoring")
                return False
            self.device.energise()
            self.unlock_count += 1
            self.last_reason, self.last_recipient = reason, recipient

            self._cancel_timer()
            self._timer = threading.Timer(duration, self.lock)
            self._timer.daemon = True
            self._timer.start()

        log.info("UNLOCKED for %.1fs (%s%s)", duration, reason,
                 f", recipient={recipient}" if recipient else "")
        bus.emit(Event.UNLOCKED, duration=duration, reason=reason,
                 recipient=recipient)
        return True

    def lock(self) -> None:
        with self._lock:
            was = self.device.is_unlocked
            self._cancel_timer()
            self.device.release()
        if was:
            log.info("RELOCKED")
            bus.emit(Event.RELOCKED)

    def wait_until_locked(self, timeout: float = 30.0) -> bool:
        end = time.time() + timeout
        while self.device.is_unlocked and time.time() < end:
            time.sleep(0.1)
        return not self.device.is_unlocked

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def cleanup(self) -> None:
        self.lock()
        self.device.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cleanup()          # fail-secure on any exit path
        return False
