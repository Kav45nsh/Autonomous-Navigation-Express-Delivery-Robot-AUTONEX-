"""
AUTONEX - Secure Delivery Robot
REAL-TIME NARRATION EDITION

Mission flow:

POWER ON
    ↓
SYSTEM CHECKS
    ↓
FACE DATABASE READY
    ↓
NAVIGATION CAMERA
    ↓
WAIT FOR MARKER 1
    ↓
MARKER 1 CONFIRMED
    ↓
MOVE
    ↓
MARKER 2 / 3 / 4
    ↓
OBSTACLE SAFETY AT ANY TIME
    ↓
MARKER 5
    ↓
DESTINATION
    ↓
FACE AUTHENTICATION
    ↓
ACCESS GRANTED
    ↓
DELIVERY BOX UNLOCKED
    ↓
DELIVERY COMPLETE
    ↓
RELOCK
    ↓
MISSION COMPLETE

------------------------------------------------------------------
WHAT CHANGED IN THIS EDITION
------------------------------------------------------------------
1. Voice is now REAL-TIME: `voice.py` speaks on a background thread,
   so every `self._say(...)` call returns almost instantly instead
   of freezing camera reads / QR detection / obstacle avoidance while
   AUTONEX talks. `_say()` now defaults to non-blocking.
2. Richer, more granular narration at every step:
   - checkpoint progress ("Checkpoint 2 of 5 complete.")
   - live confidence percentage during face authentication
   - authentication attempt counters ("Attempt 1 of 3 failed.")
   - a route "heartbeat" announcement while cruising with no events,
     so AUTONEX never goes silent for long stretches
   - more obstacle-avoidance color commentary
3. `voice.flush()` is called once at the very end of shutdown so the
   final goodbye is never cut off when the process exits.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

import cv2

from camera import CameraManager, CameraMode
from config import settings
from core import display
from core.logging_setup import setup_logging
from face_auth.face_authentication import FaceAuthenticator
from face_auth.face_database import FaceDatabase
from face_auth.face_registration import from_camera as register_from_camera
from navigation.navigation import Navigator
from navigation.robot_state import RobotState
from obstacle.obstacle_avoidance import (
    AvoidancePhase,
    ObstacleAvoidance,
)
from qr_navigation.qr_detector import QRDetector
from security.access_controller import AccessController
from voice.voice import Phrases, VoiceAnnouncer


log = logging.getLogger("robot")

# How often (seconds) AUTONEX gives a "still here, still fine" update
# while nothing else noteworthy is happening.
HEARTBEAT_INTERVAL_MOVING = 8.0
HEARTBEAT_INTERVAL_WAITING = 12.0

# How often (seconds) AUTONEX calls out a live confidence percentage
# while a face is being verified.
AUTH_VOICE_UPDATE_INTERVAL = 2.5


class SecureDeliveryRobot:

    def __init__(
        self,
        use_voice: bool = True,
        skip_registration: bool = False,
    ):

        self.skip_registration = skip_registration

        # ========================================================
        # VOICE BACKEND
        # ========================================================

        if not use_voice:
            settings.VOICE_BACKEND = "silent"

        # ========================================================
        # CORE SYSTEMS
        # ========================================================

        self.camera = CameraManager()

        self.qr = QRDetector()

        self.voice = VoiceAnnouncer()

        self.navigator = Navigator(
            voice=self.voice
        )

        self.avoidance = ObstacleAvoidance()

        self.authenticator = FaceAuthenticator()

        self.access = AccessController()

        # ========================================================
        # MISSION FLAGS
        # ========================================================

        self._running = True

        self._last_dets = []

        # ========================================================
        # QR VOICE STATE
        # ========================================================

        self._last_raw_marker = None

        self._last_confirming = False

        self._confirming_marker = None

        # ========================================================
        # CHECKPOINT PROGRESS
        # ========================================================

        self._checkpoints_done = 0

        # ========================================================
        # AUTH VOICE STATE
        # ========================================================

        self._auth_voice_started = False
        self._auth_face_announced = False
        self._auth_verifying_announced = False
        self._auth_success_announced = False
        self._auth_last_reason = None
        self._auth_last_name = None
        self._auth_last_voice_time = 0.0
        self._auth_last_confidence = -1.0

        # ========================================================
        # ROBOT STATE VOICE
        # ========================================================

        self._previous_robot_state = None

        # ========================================================
        # TURN TRACKING
        # ========================================================

        self._active_turn = None

        # ========================================================
        # MISSION VOICE FLAGS
        # ========================================================

        self._startup_announced = False
        self._waiting_announced = False
        self._destination_announced = False
        self._shutdown_announced = False

        # ========================================================
        # HEARTBEAT TRACKING
        # ========================================================

        self._last_heartbeat_time = 0.0

    # ============================================================
    # VOICE HELPER
    # ============================================================

    def _say(
        self,
        message: str,
        blocking: bool = False,
    ) -> None:
        """
        Central voice helper.

        All important mission announcements pass through here.
        Defaults to non-blocking: with the real-time async voice
        backend this means the sentence is queued and spoken on a
        background thread while the robot keeps reading frames,
        stepping the FSM, and reacting to obstacles - nothing waits
        on AUTONEX finishing a sentence unless `blocking=True` is
        explicitly requested.
        """

        if not message:
            return

        try:

            self.voice.say(
                message,
                blocking=blocking,
            )

        except Exception:

            log.exception(
                "Voice announcement failed: %s",
                message,
            )

    # ============================================================
    # MISSION
    # ============================================================

    def run(self) -> int:

        signal.signal(
            signal.SIGINT,
            self._on_signal,
        )

        signal.signal(
            signal.SIGTERM,
            self._on_signal,
        )

        self.voice.start()

        self._banner()

        try:

            # ----------------------------------------------------
            # POWER ON
            # ----------------------------------------------------

            self._say("AUTONEX power on.")

            self._say("Starting system initialization.")


            # ----------------------------------------------------
            # FACE DATABASE
            # ----------------------------------------------------

            self._ensure_face_registered()

            self._say("Authorized recipient database ready.")

            # ----------------------------------------------------
            # NAVIGATION CAMERA
            # ----------------------------------------------------

            self._say("Initializing navigation camera.")

            self.camera.open(
                CameraMode.NAVIGATION
            )

            self._say("Navigation camera ready.")

            # ----------------------------------------------------
            # SYSTEM READY
            # ----------------------------------------------------

            self._say(Phrases.STARTUP)

            self._say("Navigation system ready.")

            self._say("Obstacle detection system ready.")

            self._say("Security system ready.")


            self._waiting_announced = True

            self._last_heartbeat_time = time.monotonic()

            # ----------------------------------------------------
            # MAIN CONTROL LOOP
            # ----------------------------------------------------

            while (
                self._running
                and not self.navigator.fsm.is_terminal()
            ):

                if not self._tick():
                    break

        except Exception:

            log.exception(
                "Fatal error"
            )

            self._say(
                "A system error has occurred.",
                blocking=True,
            )

            self._say(
                "AUTONEX is entering a safe state.",
                blocking=True,
            )

            self.navigator.fsm.to(
                RobotState.ERROR,
                "exception",
                strict=False,
            )

            return 2

        finally:

            self.shutdown()

        log.info(
            "Final state: %s",
            self.navigator.fsm.state.name,
        )

        log.info(
            "States: %s",
            " | ".join(
                self.navigator.fsm.timeline()
            ),
        )

        return (
            0
            if self.navigator.fsm.state
            is RobotState.DELIVERY_UNLOCKED
            else 1
        )

    # ============================================================
    # FACE REGISTRATION
    # ============================================================

    def _ensure_face_registered(self) -> None:

        db = FaceDatabase.load()

        if (
            not db.is_empty
            or self.skip_registration
        ):

            log.info(
                "Face DB ready: %s",
                db.summary(),
            )

            return

        # Registration happens before the mission clock starts, and
        # involves an interactive terminal prompt, so it's fine (and
        # clearer for the user) to keep this part blocking.

        self._say(
            "No authorized recipient is registered.",
            blocking=True,
        )

        self._say(
            "Recipient registration is required.",
            blocking=True,
        )

        print(
            "\nNo authorized face on file yet."
        )

        print(
            "Registering the recipient now - "
            "camera will open, press SPACE to "
            "capture a photo, q when done.\n"
        )

        name = input(
            "Name of the authorized recipient: "
        ).strip() or "Recipient"

        self._say(
            "Please look at the camera for registration.",
            blocking=True,
        )

        register_from_camera(
            name,
            target=6,
        )

        self._say(
            "Recipient registration completed.",
            blocking=True,
        )

    # ============================================================
    # MAIN CONTROL TICK
    # ============================================================

    def _tick(self) -> bool:

        frame = self.camera.read()

        if frame is None:

            time.sleep(0.02)

            return True

        # ========================================================
        # QR DETECTION
        # ========================================================

        self._last_dets = self.qr.detect(
            frame
        )

        raw_marker = None

        nearest = QRDetector.nearest(
            self._last_dets
        )

        if nearest is not None:

            raw_marker = nearest.data

        # --------------------------------------------------------
        # QR DETECTION ANNOUNCEMENT
        # --------------------------------------------------------

        self._announce_marker_detection(
            raw_marker
        )

        # ========================================================
        # SAFETY FIRST
        # ========================================================

        if self.navigator.started:

            before = self.avoidance.phase

            phase = self.avoidance.update(
                self.navigator.movement
            )

            self._announce_avoidance(
                before,
                phase,
            )

            self._sync_obstacle_state(
                phase
            )

            # ----------------------------------------------------
            # OBSTACLE HAS CONTROL
            # ----------------------------------------------------

            if phase is not AvoidancePhase.CLEAR:

                self._render(frame)

                return self._continue_display()

            # ----------------------------------------------------
            # OBSTACLE CLEARED
            # ----------------------------------------------------

            if (
                before is not AvoidancePhase.CLEAR
            ):

                self._say("Obstacle cleared.")

                self._say("Resuming the original route.")

                self.navigator.resume_after_avoidance()

        # ========================================================
        # QR NAVIGATION
        # ========================================================

        previous_state = self.navigator.fsm.state

        self.navigator.step(
            raw_marker
        )

        current_state = self.navigator.fsm.state

        # --------------------------------------------------------
        # STATE CHANGE ANNOUNCEMENTS
        # --------------------------------------------------------

        self._announce_state_change(
            previous_state,
            current_state,
        )

        # --------------------------------------------------------
        # QR CONFIRMATION / ACTION
        # --------------------------------------------------------

        self._announce_confirmation(
            raw_marker
        )

        # --------------------------------------------------------
        # ROUTE HEARTBEAT - keep narrating even when nothing else
        # is happening, so long straight stretches aren't silent.
        # --------------------------------------------------------

        self._announce_heartbeat(
            current_state
        )

        # --------------------------------------------------------
        # ARRIVAL
        # --------------------------------------------------------

        if self.navigator.destination_reached:

            self._handle_arrival()

            return False

        # --------------------------------------------------------
        # STOP MARKER
        # --------------------------------------------------------

        if self.navigator.stopped_by_qr:

            self._say("Stop command detected.")

            self._say(Phrases.STOP_CONFIRMED)

            self._say("Robot movement has stopped.")

            self._say("AUTONEX will remain safely stopped.")

            log.info(
                "Robot stopped by STOP marker. "
                "Remaining safely stopped."
            )

            return False

        # ========================================================
        # DISPLAY
        # ========================================================

        self._render(frame)

        return self._continue_display()

    # ============================================================
    # ROUTE HEARTBEAT
    # ============================================================

    def _announce_heartbeat(self, current_state) -> None:
        """
        While the robot is doing something completely uneventful
        (cruising straight, or waiting for the first marker) for a
        while, give a short periodic update so the narration never
        goes quiet for too long - this is the "as much announcement
        as it can make at each step" behaviour.
        """

        now = time.monotonic()

        if current_state is RobotState.MOVING_FORWARD:

            if now - self._last_heartbeat_time >= HEARTBEAT_INTERVAL_MOVING:

                if self._last_raw_marker:

                    self._say(
                        f"Still en route. Last checkpoint passed: "
                        f"{self._last_raw_marker.title()}."
                    )

                else:

                    self._say(Phrases.HEARTBEAT_MOVING)

                self._last_heartbeat_time = now

        elif not self.navigator.started:

            if now - self._last_heartbeat_time >= HEARTBEAT_INTERVAL_WAITING:

                self._say(Phrases.HEARTBEAT_WAITING)

                self._last_heartbeat_time = now

    # ============================================================
    # QR DETECTION VOICE
    # ============================================================

    def _announce_marker_detection(
        self,
        raw_marker,
    ) -> None:
        """
        Announces each newly visible QR marker once.

        The same marker is not announced repeatedly
        while it remains continuously visible.
        """

        if raw_marker is None:
            return

        marker = (
            raw_marker
            .strip()
            .upper()
        )

        if not marker:
            return

        if marker == self._last_raw_marker:
            return

        # --------------------------------------------------------
        # NEW MARKER
        # --------------------------------------------------------

        phrase = Phrases.MARKER_DETECTED.get(
            marker
        )

        if phrase is not None:

            self._say(phrase)

        else:

            self._say(
                f"QR marker detected: {marker}."
            )

        # --------------------------------------------------------
        # PRE-START WARNING
        # --------------------------------------------------------

        if not self.navigator.started:

            if marker != "MARKER 1":

                self._say(
                    "Start marker has not been confirmed yet."
                )

            

        self._last_raw_marker = marker
        self._last_heartbeat_time = time.monotonic()

    # ============================================================
    # QR CONFIRMATION VOICE
    # ============================================================

    def _announce_confirmation(
        self,
        raw_marker,
    ) -> None:

        status = self.navigator.last_status

        if status is None:
            return

        confirming = bool(
            getattr(
                status,
                "confirming",
                False,
            )
        )

        # --------------------------------------------------------
        # CONFIRMATION STARTED
        # --------------------------------------------------------

        if (
            confirming
            and not self._last_confirming
        ):

            if raw_marker is not None:

                self._confirming_marker = (
                    raw_marker
                    .strip()
                    .upper()
                )

                marker = self._confirming_marker

                if marker == "MARKER 1":

                    self._say("Start marker detected.")

                    self._say("Confirming the start command.")

                elif marker == "MARKER 2":

                    self._say("Straight navigation marker detected.")

                    self._say("Confirming straight movement.")

                elif marker == "MARKER 3":

                    self._say("Right turn marker detected.")

                    self._say("Confirming right turn.")

                elif marker == "MARKER 4":

                    self._say("Left turn marker detected.")

                    self._say("Confirming left turn.")

                elif marker == "MARKER 5":

                    self._say("Destination marker detected.")

                    self._say("Confirming destination.")

                elif marker == "STOP":

                    self._say("Stop marker detected.")

                    self._say("Confirming stop command.")

        # --------------------------------------------------------
        # CONFIRMATION FINISHED
        # --------------------------------------------------------

        elif (
            not confirming
            and self._last_confirming
            and self._confirming_marker
        ):

            marker = self._confirming_marker

            phrase = Phrases.MARKER_CONFIRMED.get(
                marker
            )

            if phrase is not None:

                self._say(phrase)

            else:

                self._say(f"{marker} confirmed.")

            # ----------------------------------------------------
            # CHECKPOINT PROGRESS
            # ----------------------------------------------------

            if marker in Phrases.MARKER_SEQUENCE:

                self._checkpoints_done += 1

                total = len(Phrases.MARKER_SEQUENCE)

                self._say(
                    f"Checkpoint {self._checkpoints_done} of "
                    f"{total} complete."
                )

            # ----------------------------------------------------
            # START
            # ----------------------------------------------------

            if marker == "MARKER 1":

                self._say("Start command accepted.")

                self._say("AUTONEX is beginning the delivery.")

                self._say("Starting forward navigation.")

                self._waiting_announced = False

            # ----------------------------------------------------
            # STRAIGHT
            # ----------------------------------------------------

            elif marker == "MARKER 2":

                self._say("Straight path confirmed.")

                self._say("Continuing toward the destination.")

            # ----------------------------------------------------
            # RIGHT
            # ----------------------------------------------------

            elif marker == "MARKER 3":

                self._active_turn = "RIGHT"

                self._say("Right turn command accepted.")

                self._say("Preparing for a ninety degree right turn.")

            # ----------------------------------------------------
            # LEFT
            # ----------------------------------------------------

            elif marker == "MARKER 4":

                self._active_turn = "LEFT"

                self._say("Left turn command accepted.")

                self._say("Preparing for a ninety degree left turn.")

            # ----------------------------------------------------
            # DESTINATION
            # ----------------------------------------------------

            elif marker == "MARKER 5":

                self._say("Destination command accepted.")

                self._say("Delivery destination confirmed.")

            # ----------------------------------------------------
            # STOP
            # ----------------------------------------------------

            elif marker == "STOP":

                self._say("Stop command confirmed.")

            self._confirming_marker = None
            self._last_heartbeat_time = time.monotonic()

        self._last_confirming = confirming

    # ============================================================
    # ROBOT STATE VOICE
    # ============================================================

    def _announce_state_change(
        self,
        before,
        after,
    ) -> None:

        if before is after:
            return

        if after is None:
            return

        log.info(
            "VOICE STATE CHANGE: %s -> %s",
            getattr(before, "name", before),
            getattr(after, "name", after),
        )

        # --------------------------------------------------------
        # MOVING FORWARD
        # --------------------------------------------------------

        if after is RobotState.MOVING_FORWARD:

            self._say("Moving forward.")

            if self._active_turn == "RIGHT":

                self._say("Right turn complete.")

                self._say("Resuming forward movement.")

                self._active_turn = None

            elif self._active_turn == "LEFT":

                self._say("Left turn complete.")

                self._say("Resuming forward movement.")

                self._active_turn = None

        # --------------------------------------------------------
        # RIGHT TURN
        # --------------------------------------------------------

        elif (
            hasattr(RobotState, "TURNING_RIGHT")
            and after is RobotState.TURNING_RIGHT
        ):

            self._say("Turning right now.")

            self._say("Executing ninety degree right turn.")

        # --------------------------------------------------------
        # LEFT TURN
        # --------------------------------------------------------

        elif (
            hasattr(RobotState, "TURNING_LEFT")
            and after is RobotState.TURNING_LEFT
        ):

            self._say("Turning left now.")

            self._say("Executing ninety degree left turn.")

        # --------------------------------------------------------
        # OBSTACLE STATES
        # --------------------------------------------------------

        elif after is RobotState.OBSTACLE_DETECTED:

            self._say("Obstacle safety mode active.")

        # --------------------------------------------------------
        # DESTINATION
        # --------------------------------------------------------

        elif after is RobotState.AUTHENTICATING:

            self._say("Robot is stationary.")

            self._say("Entering secure authentication mode.")

        # --------------------------------------------------------
        # ACCESS DENIED
        # --------------------------------------------------------

        elif after is RobotState.ACCESS_DENIED:

            self._say("Access has been denied.")

            self._say("The delivery compartment remains locked.")

        # --------------------------------------------------------
        # DELIVERY UNLOCKED
        # --------------------------------------------------------

        elif after is RobotState.DELIVERY_UNLOCKED:

            self._say("Delivery authorization successful.")

            self._say("The recipient is authorized.")

        self._last_heartbeat_time = time.monotonic()

    # ============================================================
    # OBSTACLE VOICE
    # ============================================================

    def _announce_avoidance(
        self,
        before: AvoidancePhase,
        after: AvoidancePhase,
    ) -> None:

        if after is before:
            return

        self._last_heartbeat_time = time.monotonic()

        # --------------------------------------------------------
        # OBSTACLE DETECTED
        # --------------------------------------------------------

        if (
            after
            is AvoidancePhase.OBSTACLE_DETECTED
        ):

            self._say(Phrases.OBSTACLE_DETECTED)

            self._say("AUTONEX is stopping for safety.")

            self._say("Checking available paths.")

        # --------------------------------------------------------
        # CHECKING PATH
        # --------------------------------------------------------

        elif (
            after
            is AvoidancePhase.OBSTACLE_CHECKING
        ):

            self._say(Phrases.CHECKING_OBSTACLE)

            self._say("Checking left and right clearance.")

        # --------------------------------------------------------
        # LEFT
        # --------------------------------------------------------

        elif (
            after
            is AvoidancePhase.AVOIDING_LEFT
        ):

            self._say(Phrases.LEFT_PATH_CLEAR)

            self._say("Left side is clear.")

          

        # --------------------------------------------------------
        # RIGHT
        # --------------------------------------------------------

        elif (
            after
            is AvoidancePhase.AVOIDING_RIGHT
        ):

            self._say(Phrases.RIGHT_PATH_CLEAR)

            self._say("Right side is clear.")


        # --------------------------------------------------------
        # RETURNING TO PATH
        # --------------------------------------------------------

        elif (
            after
            is AvoidancePhase.RETURNING_TO_PATH
        ):

            self._say("Obstacle avoidance completed.")

            self._say("Returning to the original route.")

        # --------------------------------------------------------
        # BOTH BLOCKED
        # --------------------------------------------------------

        elif (
            after
            is AvoidancePhase.OBSTACLE_STOP
        ):

            self._say(Phrases.BOTH_PATHS_BLOCKED)

            self._say("Both paths are blocked.")

            self._say("Remaining stopped for safety.")

            self._say("I will recheck the path.")

        # --------------------------------------------------------
        # CLEAR
        # --------------------------------------------------------

        elif (
            after
            is AvoidancePhase.CLEAR
            and before
            is not AvoidancePhase.CLEAR
        ):

            self._say(Phrases.PATH_CLEAR)

            self._say("The path is clear.")

            self._say("Normal navigation can resume.")

    # ============================================================
    # SYNC OBSTACLE STATE
    # ============================================================

    def _sync_obstacle_state(
        self,
        phase: AvoidancePhase,
    ) -> None:

        mapping = {

            AvoidancePhase.OBSTACLE_DETECTED:
                RobotState.OBSTACLE_DETECTED,

            AvoidancePhase.OBSTACLE_CHECKING:
                RobotState.OBSTACLE_CHECKING,

            AvoidancePhase.AVOIDING_LEFT:
                RobotState.AVOIDING_LEFT,

            AvoidancePhase.AVOIDING_RIGHT:
                RobotState.AVOIDING_RIGHT,

            AvoidancePhase.RETURNING_TO_PATH:
                RobotState.RETURNING_TO_PATH,

            AvoidancePhase.OBSTACLE_STOP:
                RobotState.OBSTACLE_STOP,
        }

        target = mapping.get(
            phase
        )

        if (
            target is not None
            and self.navigator.fsm.state
            is not target
        ):

            self.navigator.fsm.to(
                target,
                f"avoidance -> {phase.name}",
                strict=False,
            )

        elif (
            phase is AvoidancePhase.CLEAR
            and self.navigator.fsm.state
            in mapping.values()
        ):

            self.navigator.fsm.to(
                RobotState.MOVING_FORWARD,
                "avoidance cleared",
                strict=False,
            )

    # ============================================================
    # ARRIVAL / FACE AUTHENTICATION
    # ============================================================

    def _handle_arrival(self) -> None:

        if self._destination_announced:
            return

        self._destination_announced = True

        # --------------------------------------------------------
        # DESTINATION
        #
        # These are all non-blocking: they get queued and narrated
        # in the background while AUTONEX immediately moves on to
        # switching the camera and starting authentication - the
        # recipient doesn't have to wait through the whole speech
        # before verification actually begins.
        # --------------------------------------------------------

        self._say(Phrases.DELIVERY_POINT_REACHED)

        self._say("AUTONEX has reached the delivery destination.")

        self._say("Stopping normal navigation.")

        self._say("QR navigation is now complete.")

        self._say("Preparing secure recipient verification.")

        # --------------------------------------------------------
        # CAMERA SWITCH
        # --------------------------------------------------------

        self._say("Switching camera to face authentication mode.")

        self.camera.set_mode(
            CameraMode.FACE_AUTH
        )

        self._say("Face authentication camera ready.")

        self.navigator.fsm.to(
            RobotState.AUTHENTICATING,
            "camera switched to FACE_AUTH",
            strict=False,
        )

        # --------------------------------------------------------
        # RECIPIENT PROMPT
        # --------------------------------------------------------

        self._say(Phrases.PLEASE_AUTHENTICATE)

        self._say("Please remain in front of the camera.")

        self._say(
            "The delivery will remain locked until your identity "
            "is verified."
        )

        # --------------------------------------------------------
        # AUTHENTICATION
        # --------------------------------------------------------

        self._auth_voice_started = True
        self._auth_face_announced = False
        self._auth_verifying_announced = False
        self._auth_success_announced = False
        self._auth_last_confidence = -1.0
        self._auth_last_voice_time = 0.0

        self._say("Starting recipient authentication.")

        self._say(Phrases.VERIFYING_RECIPIENT)

        self._say("Analyzing facial identity.")

        outcome = self.authenticator.authenticate(
            self.camera,
            on_frame=self._on_auth_frame,
        )

        # --------------------------------------------------------
        # AUTHENTICATION FINISHED
        # --------------------------------------------------------

        self._say("Face authentication process complete.")

        # --------------------------------------------------------
        # SECURITY DECISION
        # --------------------------------------------------------

        self._say("Security controller is evaluating access.")

        decision = self.access.handle(
            outcome
        )

        # ========================================================
        # AUTHORIZED
        # ========================================================

        if decision.granted:

            self._say(Phrases.AUTH_SUCCESS)

            self._say(Phrases.ACCESS_GRANTED)

            self._say("Identity verified successfully.")

            self._say(
                f"Recognized recipient: {decision.recipient}, "
                f"confidence {decision.confidence:.0%}."
            )

            self._say("Delivery access authorized.")

            self.navigator.fsm.to(
                RobotState.DELIVERY_UNLOCKED,
                (
                    f"{decision.recipient} "
                    f"@ {decision.confidence:.0%}"
                ),
                strict=False,
            )

            self._say("Unlocking delivery compartment.")

            self._say(Phrases.COMPARTMENT_OPEN)

            self._say("Delivery compartment is now unlocked.")

            self._say("Please collect your delivery.")

            self._say("The compartment will be secured automatically.")

            self._say(
                "Delivery authorization completed.",
                blocking=True,
            )

            log.info(
                "Delivery compartment opened "
                "for authorized recipient."
            )

        # ========================================================
        # DENIED
        # ========================================================

        else:

            self._say("Recipient authentication was unsuccessful.")

            attempts = getattr(outcome, "attempts", None)

            if attempts is not None:

                self._say(
                    f"Attempt {attempts} of "
                    f"{settings.AUTH_MAX_ATTEMPTS} failed."
                )

            if (
                outcome.attempts
                >= settings.AUTH_MAX_ATTEMPTS
            ):

                self._say(Phrases.LOCKOUT)

                self._say("Maximum authentication attempts reached.")

                self._say(
                    "The delivery compartment remains securely locked.",
                    blocking=True,
                )

            else:

                self._say(Phrases.AUTH_FAILED)

                self._say(
                    "Please try authentication again if attempts remain.",
                    blocking=True,
                )

            self.navigator.fsm.to(
                RobotState.ACCESS_DENIED,
                decision.reason,
                strict=False,
            )

    # ============================================================
    # AUTHENTICATION CAMERA FRAME
    # ============================================================

    def _on_auth_frame(
        self,
        frame,
        result,
        streak,
    ) -> None:

        now = time.monotonic()

        # ========================================================
        # VOICE AUTHENTICATION FEEDBACK
        # ========================================================

        if result.box:

            # ----------------------------------------------------
            # FACE FOUND
            # ----------------------------------------------------

            if not self._auth_face_announced:

                self._say("Face detected.")

                self._say("Beginning identity verification.")

                self._auth_face_announced = True

                self._auth_last_voice_time = now

            # ----------------------------------------------------
            # PERIODIC VERIFICATION UPDATE WITH LIVE PERCENTAGE
            # ----------------------------------------------------

            confidence = float(
                getattr(
                    result,
                    "confidence",
                    0.0,
                )
            )

            if (
                now - self._auth_last_voice_time
                >= AUTH_VOICE_UPDATE_INTERVAL
            ):

                if confidence >= settings.UNLOCK_CONFIDENCE_THRESHOLD:

                    self._say(
                        f"Confidence at {confidence:.0%}. "
                        f"Above the required security threshold."
                    )

                else:

                    self._say(
                        f"Confidence at {confidence:.0%}. "
                        f"Verification still in progress."
                    )

                self._auth_last_voice_time = now
                self._auth_last_confidence = confidence

            # ----------------------------------------------------
            # SUCCESS THRESHOLD CROSSING
            # ----------------------------------------------------

            if (
                confidence
                >= settings.UNLOCK_CONFIDENCE_THRESHOLD
                and not self._auth_success_announced
            ):

                self._say("Strong identity match detected.")

                self._say(
                    f"Match streak {streak[0]} of {streak[1]}."
                )

                self._say("Waiting for authentication confirmation.")

                self._auth_success_announced = True

        else:

            # ----------------------------------------------------
            # FACE LOST
            # ----------------------------------------------------

            if self._auth_face_announced:

                if (
                    now - self._auth_last_voice_time
                    >= 3.0
                ):

                    self._say("Face is no longer visible.")

                    self._say("Please face the camera again.")

                    self._auth_face_announced = False

                    self._auth_last_voice_time = now

        # ========================================================
        # DISPLAY
        # ========================================================

        if settings.HEADLESS:

            return

        if result.box:

            t, r, b, l = result.box

            ok = (
                streak[0]
                >= streak[1]
            )

            cv2.rectangle(
                frame,
                (l, t),
                (r, b),
                (0, 200, 0)
                if ok
                else
                (0, 165, 255),
                2,
            )

        cv2.putText(
            frame,
            (
                f"AUTH  "
                f"{result.name or 'UNKNOWN'}  "
                f"{result.confidence:.0%}  "
                f"[{streak[0]}/{streak[1]}]  "
                f"{result.reason}"
            ),
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

        display.show(
            "AUTONEX - Secure Delivery Robot",
            frame,
        )

        display.wait_key(1)

    # ============================================================
    # DISPLAY
    # ============================================================

    def _render(
        self,
        frame,
    ) -> None:

        if settings.HEADLESS:
            return

        QRDetector.draw(
            frame,
            self._last_dets,
        )

        text = (
            f"AUTONEX | "
            f"{self.navigator.fsm.state.name}"
        )

        if (
            self.navigator.started
            and self.avoidance.phase
            is not AvoidancePhase.CLEAR
        ):

            text += (
                f" | "
                f"avoidance: "
                f"{self.avoidance.phase.name}"
            )

        if (
            self.navigator.last_status
            and self.navigator.last_status.confirming
        ):

            text += (
                f" | confirming "
                f"{self.navigator.last_status.elapsed:.1f}s"
            )

        if self._checkpoints_done:

            text += (
                f" | checkpoint "
                f"{self._checkpoints_done}/"
                f"{len(Phrases.MARKER_SEQUENCE)}"
            )

        cv2.putText(
            frame,
            text,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 0),
            2,
        )

        display.show(
            "AUTONEX - Secure Delivery Robot",
            frame,
        )

    # ============================================================
    # DISPLAY KEY
    # ============================================================

    def _continue_display(self) -> bool:

        if (
            not settings.HEADLESS
            and display.wait_key(1)
            == ord("q")
        ):

            self._say(
                "Manual stop requested.",
                blocking=True,
            )

            self._say(
                "Stopping AUTONEX safely.",
                blocking=True,
            )

            return False

        return True

    # ============================================================
    # TERMINAL SIGNAL
    # ============================================================

    def _on_signal(
        self,
        *_args,
    ):

        log.info(
            "Interrupt received - stopping AUTONEX"
        )

        self._say("Stop signal received.")

        self._say("AUTONEX is stopping safely.")

        self._running = False

    # ============================================================
    # BANNER
    # ============================================================

    def _banner(self) -> None:

        print(
            "=" * 66
        )

        print(
            "  AUTONEX - SECURE DELIVERY ROBOT"
        )

        print(
            "=" * 66
        )

        print(
            f"  platform    : "
            f"{'Raspberry Pi 4' if settings.IS_PI else 'Laptop'}"
        )

        print(
            f"  camera      : "
            f"{settings.CAMERA_BACKEND}"
        )

        print(
            f"  motors      : "
            f"{settings.MOTOR_BACKEND}"
        )

        print(
            f"  sensors     : "
            f"{settings.RANGE_BACKEND} "
            f"(FRONT/LEFT/RIGHT)"
        )

        print(
            f"  lock        : "
            f"{settings.LOCK_BACKEND}"
        )

        print(
            f"  face engine : "
            f"{settings.FACE_BACKEND}"
        )

        print(
            f"  qr confirm  : "
            f"{settings.QR_CONFIRMATION_TIME}s"
        )

        print(
            f"  unlock rule : "
            f">={settings.UNLOCK_CONFIDENCE_THRESHOLD:.0%} "
            f"confidence, "
            f"{settings.AUTH_REQUIRED_STREAK} frame streak"
        )

        print(
            "=" * 66
        )

        print()

    # ============================================================
    # SHUTDOWN
    # ============================================================

    def shutdown(self) -> None:

        if self._shutdown_announced:
            return

        self._shutdown_announced = True

        try:

            # ----------------------------------------------------
            # MISSION RESULT ANNOUNCEMENT
            # ----------------------------------------------------

            final_state = self.navigator.fsm.state

            if final_state is RobotState.DELIVERY_UNLOCKED:

                self._say("Delivery completed successfully.")

                self._say("Recipient access was authorized.")

                self._say("Securing the delivery system.")

            elif final_state is RobotState.ACCESS_DENIED:

                self._say("Delivery was not authorized.")

                self._say("Security lock remains engaged.")

            elif final_state is RobotState.ERROR:

                self._say("Mission ended because of a system error.")

            # ----------------------------------------------------
            # STOP MOTORS
            # ----------------------------------------------------

            self._say("Stopping robot movement.")

            self.navigator.cleanup()

            # ----------------------------------------------------
            # OBSTACLE SYSTEM
            # ----------------------------------------------------

            self._say("Stopping obstacle detection.")

            self.avoidance.cleanup()

            # ----------------------------------------------------
            # SECURITY
            # ----------------------------------------------------

            self._say("Securing delivery compartment.")

            self.access.cleanup()

            self._say("Delivery compartment secured.")

            # ----------------------------------------------------
            # CAMERA
            # ----------------------------------------------------

            self._say("Closing camera system.")

            self.camera.close()

            # ----------------------------------------------------
            # FINAL
            # ----------------------------------------------------

            self._say("Mission complete.")

            self._say(
                Phrases.SHUTDOWN,
                blocking=True,
            )

        finally:

            # Make sure every queued line has actually been spoken
            # before the process exits, then tear the worker down.
            self.voice.flush()
            self.voice.stop()

            display.destroy_all()


# =================================================================
# CLI
# =================================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description="AUTONEX Secure Delivery Robot"
    )

    parser.add_argument(
        "--simulate",
        action="store_true",
        help=(
            "Force simulated motors, "
            "lock and ultrasonic sensors"
        ),
    )

    parser.add_argument(
        "--no-voice",
        action="store_true",
        help="Silence TTS while debugging",
    )

    parser.add_argument(
        "--skip-registration",
        action="store_true",
        help=(
            "Skip the pre-start face capture "
            "step"
        ),
    )

    args = parser.parse_args()

    setup_logging()

    # ============================================================
    # SIMULATION
    # ============================================================

    if args.simulate:

        settings.MOTOR_BACKEND = "simulated"

        settings.LOCK_BACKEND = "simulated"

        settings.RANGE_BACKEND = "simulated"

    # ============================================================
    # CREATE ROBOT
    # ============================================================

    robot = SecureDeliveryRobot(
        use_voice=not args.no_voice,
        skip_registration=args.skip_registration,
    )

    return robot.run()


if __name__ == "__main__":

    sys.exit(
        main()
    )