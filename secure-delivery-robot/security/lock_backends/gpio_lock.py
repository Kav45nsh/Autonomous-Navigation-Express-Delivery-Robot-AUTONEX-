"""
Raspberry Pi GPIO solenoid driver.

READ HARDWARE.md BEFORE WIRING THIS.

A GPIO pin sources ~16 mA at 3.3 V. A 12 V solenoid draws 300-600 mA.
Connecting one directly destroys the pin and possibly the Pi. You need a
MOSFET (IRLZ44N) or an opto-isolated relay module, a separate 12 V supply,
a flyback diode across the coil, and a common ground.

Safety behaviours built in here:
  - A watchdog timer force-releases after MAX_CONTINUOUS_ENERGISE_S. Solenoid
    coils are rated for intermittent duty; held on, they overheat and burn out.
  - atexit + cleanup() release the coil, so a crash leaves the box LOCKED,
    not hanging open.
"""
from __future__ import annotations

import atexit
import logging
import threading

from config import settings
from core.interfaces import LockDevice

log = logging.getLogger(__name__)


class GPIOSolenoidLock(LockDevice):
    def __init__(self, pin: int = None, active_high: bool = None):
        self.pin = settings.PIN_SOLENOID if pin is None else pin
        self.active_high = (settings.SOLENOID_ACTIVE_HIGH
                            if active_high is None else active_high)
        self._watchdog: threading.Timer | None = None
        self._unlocked = False

        try:
            from gpiozero import DigitalOutputDevice
        except ImportError as e:
            raise RuntimeError(
                "gpiozero unavailable. sudo apt install -y python3-gpiozero "
                "python3-lgpio"
            ) from e

        self._device = DigitalOutputDevice(
            self.pin, active_high=self.active_high, initial_value=False)
        atexit.register(self.cleanup)
        log.info("Solenoid on BCM %d (active_%s), starts LOCKED",
                 self.pin, "high" if self.active_high else "low")

    def energise(self) -> None:
        self._device.on()
        self._unlocked = True
        log.info("Solenoid ENERGISED - compartment open")
        self._cancel_watchdog()
        self._watchdog = threading.Timer(
            settings.MAX_CONTINUOUS_ENERGISE_S, self._watchdog_fire)
        self._watchdog.daemon = True
        self._watchdog.start()

    def _watchdog_fire(self) -> None:
        if self._unlocked:
            log.error("WATCHDOG: solenoid held %.0fs - forcing release to "
                      "protect the coil", settings.MAX_CONTINUOUS_ENERGISE_S)
            self.release()

    def _cancel_watchdog(self) -> None:
        if self._watchdog is not None:
            self._watchdog.cancel()
            self._watchdog = None

    def release(self) -> None:
        self._cancel_watchdog()
        try:
            self._device.off()
        except Exception:
            pass
        if self._unlocked:
            log.info("Solenoid released - compartment locked")
        self._unlocked = False

    @property
    def is_unlocked(self) -> bool:
        return self._unlocked

    def cleanup(self) -> None:
        self.release()
        try:
            self._device.close()
        except Exception:
            pass
