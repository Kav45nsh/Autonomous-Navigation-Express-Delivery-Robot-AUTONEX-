"""
Navigator - turns CONFIRMED QR commands into robot behaviour.

Core idea from the spec: QR codes are events, not continuous commands.
STRAIGHT keeps the robot moving even after the marker is out of view.
RIGHT/LEFT perform exactly ONE 90-degree turn and then fall back to
STRAIGHT automatically. DESTINATION and STOP are two separate, unrelated
outcomes - DESTINATION hands off to face authentication, STOP just halts.

Nothing here talks to the ultrasonic sensors. Obstacle avoidance is handled
by obstacle/obstacle_avoidance.py and is only ever a TEMPORARY interruption:
this class's `desired_command` is never changed by an obstacle. See
resume_after_avoidance().
"""
from __future__ import annotations

import logging
from typing import Optional

from navigation.movement_controller import MovementController
from navigation.robot_state import RobotState, StateMachine
from qr_navigation.marker_handler import MarkerHandler
from qr_navigation.qr_commands import QRCommandHandler
from voice.voice import Phrases

logger = logging.getLogger(__name__)


class Navigator:
    def __init__(self, movement: MovementController = None,
                 markers: MarkerHandler = None,
                 commands: QRCommandHandler = None,
                 fsm: StateMachine = None,
                 voice=None):
        self.movement = movement or MovementController()
        self.markers = markers or MarkerHandler()
        self.commands = commands or QRCommandHandler()
        self.fsm = fsm or StateMachine(RobotState.WAITING_FOR_START)
        self.voice = voice

        self.started = False                       # MARKER 1 confirmed?
        self.desired_command: Optional[str] = None  # currently "STRAIGHT" or None
        self.stopped_by_qr = False
        self.destination_reached = False
        self.last_status = None                     # last MarkerStatus (for UI)

    def _say(self, phrase: str, **fmt) -> None:
        if self.voice:
            self.voice.say(phrase, **fmt)

    # ───────────────────────────────────────────── main entry point
    def step(self, raw_qr: Optional[str]) -> None:
        """One control-loop tick of QR handling.

        Call this ONLY while obstacle avoidance is not currently in control
        of the motors (i.e. while ObstacleAvoidance.phase is CLEAR).
        `raw_qr` is the decoded text of the most prominent QR code visible
        this frame, or None if nothing is visible.
        """
        self.last_status = self.markers.update(raw_qr)
        if self.last_status.just_confirmed is None:
            return

        command = self.commands.parse(self.last_status.just_confirmed)
        if command is None:
            return  # unrecognised marker - already logged by QRCommandHandler

        self._handle(command)

    # ───────────────────────────────────────────── command handlers
    def _handle(self, command: str) -> None:
        if not self.started and command != "START":
            logger.info("Ignoring '%s' - robot has not received MARKER 1 "
                       "(START) yet", command)
            return

        if self.destination_reached or self.stopped_by_qr:
            # QR navigation has ended for this mission (destination reached,
            # or a STOP marker halted the robot) - no further marker should
            # move the robot again.
            logger.info("Ignoring '%s' - QR navigation already stopped "
                       "(destination_reached=%s, stopped_by_qr=%s)",
                       command, self.destination_reached, self.stopped_by_qr)
            return

        handler = {
            "START": self._on_start,
            "STRAIGHT": self._on_straight,
            "RIGHT": self._on_right,
            "LEFT": self._on_left,
            "DESTINATION": self._on_destination,
            "STOP": self._on_stop,
        }.get(command)

        if handler is None:
            logger.warning("No handler wired up for command '%s'", command)
            return
        handler()

    def _on_start(self) -> None:
        if self.started:
            return
        self.started = True
        self.fsm.to(RobotState.STARTING, "MARKER 1 confirmed")
        self._say(Phrases.MARKER1_START)
        self.desired_command = "STRAIGHT"
        self.movement.move_forward()
        self.fsm.to(RobotState.MOVING_FORWARD, "starting route")

    def _on_straight(self) -> None:
        self.desired_command = "STRAIGHT"
        self._say(Phrases.MARKER2_STRAIGHT)
        self.fsm.to(RobotState.MOVING_FORWARD, "MARKER 2 confirmed")
        self.movement.move_forward()

    def _on_right(self) -> None:
        self.fsm.to(RobotState.TURNING_RIGHT, "MARKER 3 confirmed")
        self._say(Phrases.MARKER3_RIGHT)
        self.movement.turn_right_90()          # exactly ONE 90-degree turn
        self.desired_command = "STRAIGHT"       # then automatically back to straight
        self.fsm.to(RobotState.MOVING_FORWARD, "turn complete")
        self.movement.move_forward()

    def _on_left(self) -> None:
        self.fsm.to(RobotState.TURNING_LEFT, "MARKER 4 confirmed")
        self._say(Phrases.MARKER4_LEFT)
        self.movement.turn_left_90()
        self.desired_command = "STRAIGHT"
        self.fsm.to(RobotState.MOVING_FORWARD, "turn complete")
        self.movement.move_forward()

    def _on_destination(self) -> None:
        self.movement.stop()
        self.desired_command = None
        self.destination_reached = True
        self._say(Phrases.DESTINATION_REACHED)
        self.fsm.to(RobotState.DESTINATION, "MARKER 5 confirmed")

    def _on_stop(self) -> None:
        """The separate STOP QR. NOT the destination - no face auth, no unlock."""
        self.movement.stop()
        self.desired_command = None
        self.stopped_by_qr = True
        self._say(Phrases.STOP_CONFIRMED)
        self.fsm.to(RobotState.STOPPED_BY_QR, "STOP confirmed")

    # ───────────────────────────────────────────── obstacle-avoidance hook
    def resume_after_avoidance(self) -> None:
        """Called once obstacle avoidance hands control back (phase -> CLEAR).
        Re-applies whatever the QR navigation command already was - obstacle
        avoidance never changes desired_command itself."""
        if (self.desired_command == "STRAIGHT"
                and not self.destination_reached
                and not self.stopped_by_qr):
            self.movement.move_forward()

    # ───────────────────────────────────────────── lifecycle
    def reset(self) -> None:
        self.started = False
        self.desired_command = None
        self.stopped_by_qr = False
        self.destination_reached = False
        self.markers.reset()

    def cleanup(self) -> None:
        self.movement.cleanup()
