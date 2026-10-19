"""
The mission state machine.

Explicit legal transitions, so an unexpected jump raises instead of silently
happening. Two families of state:

  QR navigation:
    WAITING_FOR_START -> STARTING -> MOVING_FORWARD -> TURNING_LEFT/RIGHT
                                   -> MOVING_FORWARD -> ... -> DESTINATION
                                   -> STOPPED_BY_QR (a separate concept)

  Obstacle safety (nested inside MOVING_FORWARD, always able to interrupt it):
    MOVING_FORWARD -> OBSTACLE_DETECTED -> OBSTACLE_CHECKING
        -> AVOIDING_LEFT / AVOIDING_RIGHT -> RETURNING_TO_PATH -> MOVING_FORWARD
        -> OBSTACLE_STOP (both sides blocked - keep re-checking) -> OBSTACLE_CHECKING

  Destination / delivery:
    DESTINATION -> AUTHENTICATING -> DELIVERY_UNLOCKED
                                   -> ACCESS_DENIED
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


class RobotState(Enum):
    WAITING_FOR_START = auto()
    STARTING = auto()
    MOVING_FORWARD = auto()
    TURNING_LEFT = auto()
    TURNING_RIGHT = auto()

    OBSTACLE_DETECTED = auto()
    OBSTACLE_CHECKING = auto()
    AVOIDING_LEFT = auto()
    AVOIDING_RIGHT = auto()
    RETURNING_TO_PATH = auto()
    OBSTACLE_STOP = auto()          # both sides blocked, waiting + rechecking

    STOPPED_BY_QR = auto()          # the separate STOP QR - NOT destination

    DESTINATION = auto()
    AUTHENTICATING = auto()
    DELIVERY_UNLOCKED = auto()
    ACCESS_DENIED = auto()

    ERROR = auto()
    SHUTDOWN = auto()


TRANSITIONS: Dict[RobotState, Set[RobotState]] = {
    RobotState.WAITING_FOR_START: {RobotState.STARTING, RobotState.ERROR,
                                    RobotState.SHUTDOWN},
    RobotState.STARTING:          {RobotState.MOVING_FORWARD, RobotState.ERROR,
                                    RobotState.SHUTDOWN},
    RobotState.MOVING_FORWARD:    {RobotState.TURNING_LEFT, RobotState.TURNING_RIGHT,
                                    RobotState.OBSTACLE_DETECTED,
                                    RobotState.STOPPED_BY_QR, RobotState.DESTINATION,
                                    RobotState.ERROR, RobotState.SHUTDOWN},
    RobotState.TURNING_LEFT:      {RobotState.MOVING_FORWARD, RobotState.ERROR,
                                    RobotState.SHUTDOWN},
    RobotState.TURNING_RIGHT:     {RobotState.MOVING_FORWARD, RobotState.ERROR,
                                    RobotState.SHUTDOWN},

    RobotState.OBSTACLE_DETECTED: {RobotState.OBSTACLE_CHECKING, RobotState.ERROR,
                                    RobotState.SHUTDOWN},
    RobotState.OBSTACLE_CHECKING: {RobotState.AVOIDING_LEFT, RobotState.AVOIDING_RIGHT,
                                    RobotState.OBSTACLE_STOP, RobotState.MOVING_FORWARD,
                                    RobotState.ERROR, RobotState.SHUTDOWN},
    RobotState.AVOIDING_LEFT:     {RobotState.RETURNING_TO_PATH, RobotState.ERROR,
                                    RobotState.SHUTDOWN},
    RobotState.AVOIDING_RIGHT:    {RobotState.RETURNING_TO_PATH, RobotState.ERROR,
                                    RobotState.SHUTDOWN},
    RobotState.RETURNING_TO_PATH: {RobotState.MOVING_FORWARD, RobotState.ERROR,
                                    RobotState.SHUTDOWN},
    RobotState.OBSTACLE_STOP:     {RobotState.OBSTACLE_CHECKING, RobotState.ERROR,
                                    RobotState.SHUTDOWN},

    RobotState.STOPPED_BY_QR:     {RobotState.SHUTDOWN},

    RobotState.DESTINATION:       {RobotState.AUTHENTICATING, RobotState.ERROR,
                                    RobotState.SHUTDOWN},
    RobotState.AUTHENTICATING:    {RobotState.DELIVERY_UNLOCKED,
                                    RobotState.ACCESS_DENIED, RobotState.ERROR,
                                    RobotState.SHUTDOWN},
    RobotState.DELIVERY_UNLOCKED: {RobotState.SHUTDOWN},
    RobotState.ACCESS_DENIED:     {RobotState.SHUTDOWN},

    RobotState.ERROR:   {RobotState.SHUTDOWN},
    RobotState.SHUTDOWN: set(),
}


@dataclass
class StateChange:
    frm: RobotState
    to: RobotState
    at: float
    note: str = ""


class StateMachine:
    def __init__(self, initial: RobotState = RobotState.WAITING_FOR_START):
        self._state = initial
        self.history: List[StateChange] = []
        self._entered_at = time.time()

    @property
    def state(self) -> RobotState:
        return self._state

    @property
    def time_in_state(self) -> float:
        return time.time() - self._entered_at

    def can(self, to: RobotState) -> bool:
        return to in TRANSITIONS.get(self._state, set())

    def to(self, new: RobotState, note: str = "", strict: bool = True) -> bool:
        if new is self._state:
            return False
        if not self.can(new):
            msg = f"Illegal transition {self._state.name} -> {new.name}"
            if strict:
                raise ValueError(msg)
            logger.warning(msg)
            return False
        logger.info("STATE %s -> %s%s", self._state.name, new.name,
                   f" ({note})" if note else "")
        self.history.append(StateChange(self._state, new, time.time(), note))
        self._state, self._entered_at = new, time.time()
        return True

    def is_terminal(self) -> bool:
        return self._state in (RobotState.SHUTDOWN, RobotState.DELIVERY_UNLOCKED,
                                RobotState.ACCESS_DENIED, RobotState.STOPPED_BY_QR)

    def timeline(self) -> List[str]:
        return [f"{c.frm.name} -> {c.to.name}" for c in self.history]
