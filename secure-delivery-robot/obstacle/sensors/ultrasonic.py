"""
HC-SR04 ultrasonic rangefinder on the Pi - one instance per position
(FRONT, LEFT, RIGHT), each wired to its own trig/echo pin pair.

WARNING: the ECHO pin outputs 5V. Feeding that into a 3.3V GPIO can damage
the Pi. Use a voltage divider (1k + 2k) or a level shifter. See HARDWARE.md.

Readings are noisy - a median of RANGE_SAMPLE_COUNT samples removes the
occasional wild spike that would otherwise trigger a phantom emergency stop.
"""
import logging
import statistics
from typing import Optional

from config import settings
from core.interfaces import RangeSensor

logger = logging.getLogger(__name__)

_PINS = {
    "FRONT": (settings.PIN_ULTRASONIC_FRONT_TRIG, settings.PIN_ULTRASONIC_FRONT_ECHO),
    "LEFT":  (settings.PIN_ULTRASONIC_LEFT_TRIG,  settings.PIN_ULTRASONIC_LEFT_ECHO),
    "RIGHT": (settings.PIN_ULTRASONIC_RIGHT_TRIG, settings.PIN_ULTRASONIC_RIGHT_ECHO),
}


class UltrasonicSensor(RangeSensor):
    def __init__(self, position: str, trig: int = None, echo: int = None):
        if position not in _PINS:
            raise ValueError(f"position must be one of {list(_PINS)}, got {position!r}")
        self.position = position

        try:
            from gpiozero import DistanceSensor
        except ImportError as e:
            raise RuntimeError(
                "gpiozero unavailable. sudo apt install -y python3-gpiozero "
                "python3-lgpio") from e

        default_trig, default_echo = _PINS[position]
        self._sensor = DistanceSensor(
            echo=default_echo if echo is None else echo,
            trigger=default_trig if trig is None else trig,
            max_distance=settings.RANGE_MAX_CM / 100.0)
        logger.info("Ultrasonic[%s] ready (trig=%s echo=%s)", position,
                   default_trig if trig is None else trig,
                   default_echo if echo is None else echo)

    def read_cm(self) -> Optional[float]:
        samples = []
        for _ in range(settings.RANGE_SAMPLE_COUNT):
            try:
                samples.append(self._sensor.distance * 100.0)
            except Exception:
                continue
        if not samples:
            return None
        return float(statistics.median(samples))

    def cleanup(self) -> None:
        try:
            self._sensor.close()
        except Exception:
            pass
