"""
Low-level movement primitives - everything that actually commands the wheels.

Kept separate from navigation.py so "what should the robot do" (QR / obstacle
logic) and "how do the motors actually do it" (timing, PWM) can be tested and
tuned independently.

move_forward() / stop() / turn_left_90() / turn_right_90() are exactly the
laptop-simulated primitives you described. The 90-degree turns currently use
a calibrated time delay (settings.TURN_DURATION) - that is fine for laptop
testing and early bring-up, but it is NOT the final physical implementation.
A fixed time does not always equal exactly 90 degrees once the robot is
carrying its own weight, the floor surface changes, or the battery sags.
Before relying on this for the real robot, replace the timing in
`_timed()` with feedback from wheel encoders or an IMU heading reading -
the public API (turn_left_90/turn_right_90) does not need to change for that
upgrade.
"""
from __future__ import annotations

import logging
import time

from config import settings
from core.interfaces import MotorDriver

logger = logging.getLogger(__name__)


def build_motors() -> MotorDriver:
    if settings.MOTOR_BACKEND == "gpio":
        from navigation.motors.gpio_motors import GPIOMotors
        return GPIOMotors()
    from navigation.motors.simulated import SimulatedMotors
    return SimulatedMotors()


class MovementController:
    def __init__(self, motors: MotorDriver = None):
        self.motors = motors or build_motors()
        self.speed = settings.DEFAULT_SPEED
        self._stopped = True

    # ───────────────────────────────────── basic primitives
    def move_forward(self, speed: float = None) -> None:
        s = self.speed if speed is None else speed
        self.motors.set_speeds(s, s)
        self._stopped = False

    # Backward-compatible alias used by a couple of internal helpers.
    forward = move_forward

    def backward(self, speed: float = None) -> None:
        s = self.speed if speed is None else speed
        self.motors.set_speeds(-s, -s)
        self._stopped = False

    def spin_left(self, speed: float = None) -> None:
        s = self.speed if speed is None else speed
        self.motors.set_speeds(-s, s)
        self._stopped = False

    def spin_right(self, speed: float = None) -> None:
        s = self.speed if speed is None else speed
        self.motors.set_speeds(s, -s)
        self._stopped = False

    def stop(self) -> None:
        self.motors.stop()
        self._stopped = True

    @property
    def is_stopped(self) -> bool:
        return self._stopped

    # ───────────────────────────────────── QR-triggered manoeuvres
    def turn_left_90(self, duration: float = None) -> None:
        """One 90-degree left turn, then stop. navigation.py is responsible
        for calling move_forward() again afterwards."""
        self._timed(self.spin_left, settings.TURN_DURATION if duration is None
                    else duration)

    def turn_right_90(self, duration: float = None) -> None:
        """One 90-degree right turn, then stop."""
        self._timed(self.spin_right, settings.TURN_DURATION if duration is None
                    else duration)

    # ───────────────────────────────────── obstacle-avoidance manoeuvres
    # Deliberately separate from the QR turns above: this is a SMALL,
    # temporary sideways nudge to get around an obstacle, not a route turn.
    def avoid_left(self, duration: float = None) -> None:
        self._timed(self.spin_left, settings.AVOIDANCE_TURN_DURATION
                    if duration is None else duration)

    def avoid_right(self, duration: float = None) -> None:
        self._timed(self.spin_right, settings.AVOIDANCE_TURN_DURATION
                    if duration is None else duration)

    def _timed(self, action, duration: float) -> None:
        action()
        time.sleep(duration)
        self.stop()

    def set_speed(self, speed: float) -> None:
        self.speed = max(0.0, min(1.0, speed))
        logger.debug("Base speed -> %.2f", self.speed)

    def cleanup(self) -> None:
        self.motors.cleanup()
