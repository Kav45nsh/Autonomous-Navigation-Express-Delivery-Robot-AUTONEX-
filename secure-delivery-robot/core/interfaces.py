"""
Hardware contracts. Every driver implements one of these.

This is the entire migration strategy: your logic imports these ABCs, never
cv2.VideoCapture or gpiozero. Swapping laptop -> Pi 4 is a config change
because both sides satisfy the same interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np


class CameraSource(ABC):
    """A camera yielding BGR numpy frames."""

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read(self) -> Optional[np.ndarray]: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def configure(self, width: int, height: int, fps: int) -> None:
        """Reconfigure resolution/framerate. Must be safe while open."""

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class MotorDriver(ABC):
    """Differential drive. Speeds are floats in [-1.0, 1.0]."""

    @abstractmethod
    def set_speeds(self, left: float, right: float) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    def cleanup(self) -> None:
        self.stop()

    @staticmethod
    def clamp(v: float) -> float:
        return max(-1.0, min(1.0, float(v)))


class LockDevice(ABC):
    """A solenoid, relay or servo lock. Fail-secure by contract."""

    @abstractmethod
    def energise(self) -> None:
        """Retract the bolt (open). Must respect MAX_CONTINUOUS_ENERGISE_S."""

    @abstractmethod
    def release(self) -> None:
        """De-energise (locked). Must be idempotent and crash-safe."""

    @property
    @abstractmethod
    def is_unlocked(self) -> bool: ...

    def cleanup(self) -> None:
        self.release()


class RangeSensor(ABC):
    """Distance sensor. Returns centimetres, or None on a bad reading."""

    @abstractmethod
    def read_cm(self) -> Optional[float]: ...

    def cleanup(self) -> None:
        pass


class Transport(ABC):
    """A byte pipe to a co-processor (ESP32) or ground station."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def send(self, line: str) -> None: ...

    @abstractmethod
    def receive(self) -> Optional[str]: ...

    @abstractmethod
    def close(self) -> None: ...
