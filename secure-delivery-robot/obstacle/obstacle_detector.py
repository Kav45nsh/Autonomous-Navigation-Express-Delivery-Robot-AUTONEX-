"""
Reads the THREE ultrasonic sensors (FRONT, LEFT, RIGHT) and turns the raw
distances into a "clearance snapshot" that the avoidance state machine
(obstacle_avoidance.py) can make a decision from.

    FRONT  -> is something in the robot's current path?
    LEFT   -> is there enough room for the robot's BODY to pass on the left?
    RIGHT  -> is there enough room for the robot's BODY to pass on the right?

The side checks are NOT a bare distance comparison. A side sensor reading
"50 cm" does not mean the robot fits - see Clearance.side_clear(), which
accounts for the robot's own width and a safety margin (both configurable in
config/settings.py).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from config import settings
from core.interfaces import RangeSensor

logger = logging.getLogger(__name__)


def build_range_sensor(position: str) -> RangeSensor:
    if settings.RANGE_BACKEND == "ultrasonic":
        from obstacle.sensors.ultrasonic import UltrasonicSensor
        return UltrasonicSensor(position)
    from obstacle.sensors.simulated_range import SimulatedRangeSensor
    return SimulatedRangeSensor()


@dataclass
class Clearance:
    front_cm: Optional[float]
    left_cm: Optional[float]
    right_cm: Optional[float]

    @property
    def front_blocked(self) -> bool:
        """True when something has entered the robot's path."""
        return (self.front_cm is not None
                and self.front_cm < settings.FRONT_SAFE_DISTANCE_CM)

    @staticmethod
    def _clear(cm: Optional[float]) -> bool:
        if cm is None or cm < settings.SIDE_SAFE_DISTANCE_CM:
            return False
        required = settings.ROBOT_WIDTH_CM + settings.SIDE_SAFETY_MARGIN_CM
        return cm >= required

    @property
    def left_clear(self) -> bool:
        return self._clear(self.left_cm)

    @property
    def right_clear(self) -> bool:
        return self._clear(self.right_cm)


class ObstacleDetector:
    def __init__(self, front: RangeSensor = None, left: RangeSensor = None,
                 right: RangeSensor = None):
        self.front = front or build_range_sensor("FRONT")
        self.left = left or build_range_sensor("LEFT")
        self.right = right or build_range_sensor("RIGHT")

    def read(self) -> Clearance:
        return Clearance(self.front.read_cm(), self.left.read_cm(),
                         self.right.read_cm())

    def cleanup(self) -> None:
        for sensor in (self.front, self.left, self.right):
            sensor.cleanup()
