"""Fake motors: logs commands and dead-reckons a pose so you can verify steering."""
import logging
import math
import time

from core.interfaces import MotorDriver

log = logging.getLogger(__name__)


class SimulatedMotors(MotorDriver):
    WHEEL_BASE_M = 0.15
    MAX_SPEED_MPS = 0.30

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.left = self.right = 0.0
        self.x = self.y = self.theta = 0.0
        self._t = time.time()
        self.command_count = 0

    def _integrate(self):
        now = time.time()
        dt, self._t = now - self._t, now
        vl, vr = self.left * self.MAX_SPEED_MPS, self.right * self.MAX_SPEED_MPS
        v, w = (vl + vr) / 2.0, (vr - vl) / self.WHEEL_BASE_M
        self.x += v * math.cos(self.theta) * dt
        self.y += v * math.sin(self.theta) * dt
        self.theta += w * dt

    def set_speeds(self, left: float, right: float) -> None:
        self._integrate()
        self.left, self.right = self.clamp(left), self.clamp(right)
        self.command_count += 1
        if self.verbose:
            log.debug("L=%+.2f R=%+.2f | x=%.2f y=%.2f th=%.0f",
                      self.left, self.right, self.x, self.y,
                      math.degrees(self.theta))

    def stop(self) -> None:
        self.set_speeds(0.0, 0.0)

    @property
    def pose(self):
        self._integrate()
        return (self.x, self.y, self.theta)
