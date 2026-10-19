"""
Obstacle avoidance state machine - "think about it, don't just always turn
left".

    MOVING_FORWARD
        |  front sensor says something is too close
        v
    OBSTACLE_DETECTED  -> stop
        v
    OBSTACLE_CHECKING  -> measure LEFT and RIGHT, decide
        |            |               |
    left clear   right clear   BOTH BLOCKED
        v            v               v
    AVOIDING_LEFT  AVOIDING_RIGHT   OBSTACLE_STOP (keep re-checking)
        v            v
    RETURNING_TO_PATH  <-------------+
        v
    back to CLEAR - Navigator resumes whatever it was already doing

IMPORTANT: this class NEVER changes Navigator.desired_command. Obstacle
avoidance is a TEMPORARY, safety-priority interruption of movement - the
original QR command (e.g. STRAIGHT) is exactly what it was before the
obstacle appeared. main.py is the one place that wires "avoidance became
CLEAR again" back to Navigator.resume_after_avoidance().

LIMITATION (documented, not hidden): the "go around and come back" manoeuvre
below is timed (AVOIDANCE_TURN_DURATION / AVOIDANCE_FORWARD_DURATION), the
same limitation described for the 90-degree QR turns in
movement_controller.py. A fixed time is not a fixed distance/angle once the
robot carries real weight and drives on a real floor. For a more reliable
return-to-path, upgrade this to use wheel encoders and/or an IMU heading to
know exactly how far the robot has actually turned/travelled, rather than
trusting the clock. The AvoidancePhase state machine below does not need to
change for that upgrade - only the bodies of AVOIDING_LEFT/AVOIDING_RIGHT/
RETURNING_TO_PATH would.
"""
from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Optional

from config import settings
from navigation.movement_controller import MovementController
from obstacle.obstacle_detector import Clearance, ObstacleDetector

logger = logging.getLogger(__name__)


class AvoidancePhase(Enum):
    CLEAR = auto()
    OBSTACLE_DETECTED = auto()
    OBSTACLE_CHECKING = auto()
    AVOIDING_LEFT = auto()
    AVOIDING_RIGHT = auto()
    RETURNING_TO_PATH = auto()
    OBSTACLE_STOP = auto()          # both sides blocked - remain stopped


class ObstacleAvoidance:
    def __init__(self, detector: ObstacleDetector = None):
        self.detector = detector or ObstacleDetector()
        self.phase = AvoidancePhase.CLEAR
        self.last_reading: Optional[Clearance] = None
        self.chosen_side: Optional[str] = None
        self._last_recheck = 0.0

    @property
    def is_active(self) -> bool:
        """True while avoidance has temporarily taken control of the motors."""
        return self.phase is not AvoidancePhase.CLEAR

    def update(self, movement: MovementController) -> AvoidancePhase:
        """Call once per control-loop tick while the robot is supposed to be
        moving. Returns the current phase. When this returns CLEAR, the
        caller should tell Navigator to resume (resume_after_avoidance())."""
        reading = self.detector.read()
        self.last_reading = reading

        # A transient obstacle that has already moved away, while we were
        # still only stopped/checking (not yet mid-manoeuvre): just resume.
        if (self.phase in (AvoidancePhase.OBSTACLE_DETECTED,
                           AvoidancePhase.OBSTACLE_CHECKING,
                           AvoidancePhase.OBSTACLE_STOP)
                and not reading.front_blocked):
            logger.info("Obstacle cleared before manoeuvring - resuming")
            self.reset()
            return self.phase

        if self.phase is AvoidancePhase.CLEAR:
            if reading.front_blocked:
                logger.warning("Obstacle detected at %.0fcm - stopping",
                               reading.front_cm if reading.front_cm else -1)
                movement.stop()
                self.phase = AvoidancePhase.OBSTACLE_DETECTED
            return self.phase

        if self.phase is AvoidancePhase.OBSTACLE_DETECTED:
            movement.stop()
            self.phase = AvoidancePhase.OBSTACLE_CHECKING
            return self.phase

        if self.phase is AvoidancePhase.OBSTACLE_CHECKING:
            return self._choose_side(reading, movement)

        if self.phase is AvoidancePhase.OBSTACLE_STOP:
            now = time.time()
            movement.stop()
            if now - self._last_recheck < settings.OBSTACLE_RECHECK_INTERVAL:
                return self.phase
            self._last_recheck = now
            return self._choose_side(reading, movement)

        if self.phase is AvoidancePhase.AVOIDING_LEFT:
            movement.avoid_left()
            movement.move_forward()
            time.sleep(settings.AVOIDANCE_FORWARD_DURATION)
            self.phase = AvoidancePhase.RETURNING_TO_PATH
            return self.phase

        if self.phase is AvoidancePhase.AVOIDING_RIGHT:
            movement.avoid_right()
            movement.move_forward()
            time.sleep(settings.AVOIDANCE_FORWARD_DURATION)
            self.phase = AvoidancePhase.RETURNING_TO_PATH
            return self.phase

        if self.phase is AvoidancePhase.RETURNING_TO_PATH:
            # Steer back the opposite way from the sidestep to straighten out.
            if self.chosen_side == "LEFT":
                movement.avoid_right()
            else:
                movement.avoid_left()
            logger.info("Back on path - handing control back to navigation")
            self.reset()
            return self.phase

        return self.phase

    def _choose_side(self, reading: Clearance,
                      movement: MovementController) -> AvoidancePhase:
        """Pick a side ONLY if it is actually safe - never 'left by default'.
        If both are safe, prefer the side with more room (a simple,
        deterministic, explainable policy)."""
        left_ok, right_ok = reading.left_clear, reading.right_clear

        if left_ok and right_ok:
            side = "LEFT" if (reading.left_cm or 0) >= (reading.right_cm or 0) else "RIGHT"
        elif left_ok:
            side = "LEFT"
        elif right_ok:
            side = "RIGHT"
        else:
            logger.warning("Both sides blocked (L=%.0fcm R=%.0fcm) - "
                           "remaining stopped, will re-check",
                           reading.left_cm if reading.left_cm else -1,
                           reading.right_cm if reading.right_cm else -1)
            movement.stop()
            self.phase = AvoidancePhase.OBSTACLE_STOP
            return self.phase

        self.chosen_side = side
        logger.info("Choosing %s (L=%.0fcm R=%.0fcm, need >= %.0fcm)", side,
                   reading.left_cm if reading.left_cm else -1,
                   reading.right_cm if reading.right_cm else -1,
                   settings.ROBOT_WIDTH_CM + settings.SIDE_SAFETY_MARGIN_CM)
        self.phase = (AvoidancePhase.AVOIDING_LEFT if side == "LEFT"
                     else AvoidancePhase.AVOIDING_RIGHT)
        return self.phase

    def reset(self) -> None:
        self.phase = AvoidancePhase.CLEAR
        self.chosen_side = None

    def cleanup(self) -> None:
        self.detector.cleanup()
