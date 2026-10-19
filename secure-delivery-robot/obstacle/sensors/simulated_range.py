"""
Fake range sensor for laptop testing.

Note the _UNSET sentinel: force(None) must mean "simulate a FAILED reading",
which is different from "nothing is forced". Using None for both would make
it impossible to test how the robot handles sensor dropouts — and ultrasonic
sensors drop readings constantly on soft or angled surfaces.
"""
from typing import List, Optional

from core.interfaces import RangeSensor

_UNSET = object()


class SimulatedRangeSensor(RangeSensor):
    def __init__(self, sequence: List[float] = None, default: float = 150.0):
        self.sequence = list(sequence) if sequence else []
        self.default = default
        self._forced = _UNSET
        self.read_count = 0

    def read_cm(self) -> Optional[float]:
        self.read_count += 1
        if self._forced is not _UNSET:
            return self._forced          # may legitimately be None
        if self.sequence:
            return self.sequence.pop(0)
        return self.default

    def force(self, cm: Optional[float]) -> None:
        """Pin the next readings. force(None) simulates a failed reading."""
        self._forced = cm

    def unforce(self) -> None:
        self._forced = _UNSET
