"""
Pi 4 motor driver via gpiozero (RPi.GPIO is deprecated on newer boards).

Assumes an L298N / TB6612FNG H-bridge: two direction pins plus one PWM enable
pin per side. NEVER power motors from the Pi's 5V rail — separate battery,
grounds tied together. See HARDWARE.md.
"""
import logging

from config import settings
from core.interfaces import MotorDriver

log = logging.getLogger(__name__)


class GPIOMotors(MotorDriver):
    def __init__(self):
        try:
            from gpiozero import Motor, PWMOutputDevice
        except ImportError as e:
            raise RuntimeError(
                "gpiozero unavailable. sudo apt install -y python3-gpiozero "
                "python3-lgpio") from e

        self._left = Motor(forward=settings.PIN_LEFT_FORWARD,
                           backward=settings.PIN_LEFT_BACKWARD)
        self._right = Motor(forward=settings.PIN_RIGHT_FORWARD,
                            backward=settings.PIN_RIGHT_BACKWARD)
        self._len = PWMOutputDevice(settings.PIN_LEFT_ENABLE,
                                    frequency=settings.PWM_FREQUENCY)
        self._ren = PWMOutputDevice(settings.PIN_RIGHT_ENABLE,
                                    frequency=settings.PWM_FREQUENCY)
        log.info("GPIO motors ready")

    def set_speeds(self, left: float, right: float) -> None:
        left, right = self.clamp(left), self.clamp(right)
        self._len.value, self._ren.value = abs(left), abs(right)
        for motor, v in ((self._left, left), (self._right, right)):
            if v > 0.01:
                motor.forward()
            elif v < -0.01:
                motor.backward()
            else:
                motor.stop()

    def stop(self) -> None:
        self._left.stop()
        self._right.stop()
        self._len.value = self._ren.value = 0.0

    def cleanup(self) -> None:
        self.stop()
        for d in (self._left, self._right, self._len, self._ren):
            try:
                d.close()
            except Exception:
                pass
