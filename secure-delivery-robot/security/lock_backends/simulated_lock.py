"""Fake solenoid for laptop development. Prints loudly so you cannot miss it."""
import logging
import time

from core.interfaces import LockDevice

log = logging.getLogger(__name__)


class SimulatedLock(LockDevice):
    def __init__(self):
        self._unlocked = False
        self.energise_count = 0
        self.last_energised_at = None

    def energise(self) -> None:
        self._unlocked = True
        self.energise_count += 1
        self.last_energised_at = time.time()
        log.info("SIMULATED LOCK: energised (bolt retracted - OPEN)")
        print("\n  ╔══════════════════════════════════════╗")
        print("  ║   COMPARTMENT UNLOCKED  (simulated)  ║")
        print("  ╚══════════════════════════════════════╝\n")

    def release(self) -> None:
        if self._unlocked:
            log.info("SIMULATED LOCK: released (bolt extended - LOCKED)")
        self._unlocked = False

    @property
    def is_unlocked(self) -> bool:
        return self._unlocked
