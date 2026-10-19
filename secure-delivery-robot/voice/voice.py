"""
AUTONEX Voice System
Windows / pyttsx3 - REAL-TIME, non-blocking edition

Compatible with:
- main.py
- navigation/navigation.py
- qr_navigation/
- face_auth/
- security/

WHY THIS VERSION IS DIFFERENT
------------------------------------------------------------------
The previous version created a fresh pyttsx3 engine for every
announcement AND spoke it synchronously on the caller's thread
(`engine.runAndWait()`), completely ignoring the `blocking` flag
that main.py was already passing around. That meant every single
`self.voice.say(...)` call - even ones meant to be quick, fire-and-
forget status updates - froze the entire control loop (camera reads,
QR detection, obstacle avoidance, navigation stepping) until the
sentence finished being spoken out loud.

This version fixes that by moving all speech onto a dedicated
background worker thread with its own queue:

    caller thread (main control loop)      voice worker thread
    ----------------------------------     ----------------------------
    say("Obstacle detected.")  ---enqueue-->  dequeue -> speak (blocking
    <- returns almost instantly                          on ITS thread)
    keeps reading camera frames                dequeue next -> speak
    keeps stepping the FSM                     ...

Messages are still spoken in the exact order they were queued (FIFO),
so the mission narration stays coherent - it just no longer holds the
robot's sensors and actuators hostage while AUTONEX is talking.

`blocking=True` is still supported for the rare case where you truly
need to wait for a specific line to finish (e.g. right before program
exit), but the DEFAULT is now non-blocking, which is what you want for
"real time" announcements at every step.

A fresh pyttsx3 engine is still created per utterance (this keeps the
original Windows-hang workaround), it just now happens off the hot
path.
"""

import logging
import queue
import threading
import time

import pyttsx3


logger = logging.getLogger(__name__)


class Phrases:

    # ============================================================
    # STARTUP
    # ============================================================

    POWER_ON = "AUTONEX power on."

    INITIALIZING = "Starting system initialization."

    CHECKING_SYSTEMS = "Checking robot systems."

    CHECKING_FACE_DATABASE = (
        "Checking authorized recipient database."
    )

    FACE_DATABASE_READY = (
        "Authorized recipient database ready."
    )

    INITIALIZING_CAMERA = (
        "Initializing navigation camera."
    )

    CAMERA_READY = (
        "Navigation camera ready."
    )

    NAVIGATION_READY = (
        "Navigation system ready."
    )

    OBSTACLE_READY = (
        "Obstacle detection system ready."
    )

    SECURITY_READY = (
        "Security system ready."
    )

    LOCK_READY = (
        "Delivery compartment security ready."
    )

    STARTUP = (
        "Hello everyone. I'm AUTONEX, your secure delivery partner."
    )

    SYSTEM_READY = (
        "All systems are ready. Mission commencing."
    )

    QR_ACTIVE = (
        "QR navigation is now active."
    )

    WAITING_FOR_START = (
        "Waiting for the start marker."
    )

    # ============================================================
    # GENERIC QR MARKER ANNOUNCEMENTS
    # ============================================================

    MARKER_DETECTED = {
        "MARKER 1": "Start marker detected.",
        "MARKER 2": "Straight navigation marker detected.",
        "MARKER 3": "Right turn marker detected.",
        "MARKER 4": "Left turn marker detected.",
        "MARKER 5": "Destination marker detected.",
        "STOP": "Stop marker detected.",
    }

    MARKER_CONFIRMING = {
        "MARKER 1": "Confirming the start command.",
        "MARKER 2": "Confirming straight movement.",
        "MARKER 3": "Confirming right turn.",
        "MARKER 4": "Confirming left turn.",
        "MARKER 5": "Confirming destination.",
        "STOP": "Confirming stop command.",
    }

    # ------------------------------------------------------------
    # IMPORTANT:
    # main.py calls MARKER_CONFIRMED.get(...)
    # ------------------------------------------------------------

    MARKER_CONFIRMED = {
        "MARKER 1": (
            "Start command confirmed."
        ),

        "MARKER 2": (
            "Straight movement confirmed."
        ),

        "MARKER 3": (
            "Right turn command confirmed."
        ),

        "MARKER 4": (
            "Left turn command confirmed."
        ),

        "MARKER 5": (
            "Destination confirmed."
        ),

        "STOP": (
            "Stop command confirmed."
        ),
    }

    # ------------------------------------------------------------
    # Checkpoint index of each marker along the route, used for
    # "step X of Y" progress narration.
    # ------------------------------------------------------------

    MARKER_SEQUENCE = [
        "MARKER 1",
        "MARKER 2",
        "MARKER 3",
        "MARKER 4",
        "MARKER 5",
    ]

    # ============================================================
    # MARKER 1 / START
    # ============================================================

    MARKER1_START = (
        "Start command confirmed. AUTONEX is beginning the delivery."
    )

    START_MARKER_DETECTED = (
        "Start marker detected."
    )

    CONFIRMING_START = (
        "Confirming the start command."
    )

    START_CONFIRMED = (
        "Start command confirmed. AUTONEX is beginning the delivery."
    )

    START_ACCEPTED = (
        "Start command accepted."
    )

    STARTING_NAVIGATION = (
        "Starting forward navigation."
    )

    # ============================================================
    # MARKER 2 / STRAIGHT
    # ============================================================

    MARKER2_STRAIGHT = (
        "Straight navigation command confirmed. Continuing forward."
    )

    STRAIGHT_MARKER_DETECTED = (
        "Straight navigation marker detected."
    )

    FORWARD_MARKER_DETECTED = (
        "Forward marker detected."
    )

    CONFIRMING_STRAIGHT = (
        "Confirming straight movement."
    )

    STRAIGHT_CONFIRMED = (
        "Straight path confirmed."
    )

    CONTINUING_FORWARD = (
        "Continuing toward the destination."
    )

    MOVING_FORWARD = (
        "Moving forward."
    )

    CONTINUE_STRAIGHT = (
        "Continuing straight."
    )

    # ============================================================
    # MARKER 3 / RIGHT
    # ============================================================

    MARKER3_RIGHT = (
        "Right turn command confirmed. Executing the turn now."
    )

    RIGHT_MARKER_DETECTED = (
        "Right turn marker detected."
    )

    CONFIRMING_RIGHT = (
        "Confirming right turn."
    )

    RIGHT_CONFIRMED = (
        "Right turn command confirmed. Executing the turn now."
    )

    RIGHT_TURN_START = (
        "Preparing for a ninety degree right turn."
    )

    RIGHT_TURN_COMPLETE = (
        "Right turn complete. Continuing forward."
    )

    # ============================================================
    # MARKER 4 / LEFT
    # ============================================================

    MARKER4_LEFT = (
        "Left turn command confirmed. Executing the turn now."
    )

    LEFT_MARKER_DETECTED = (
        "Left turn marker detected."
    )

    CONFIRMING_LEFT = (
        "Confirming left turn."
    )

    LEFT_CONFIRMED = (
        "Left turn command confirmed. Executing the turn now."
    )

    LEFT_TURN_START = (
        "Preparing for a ninety degree left turn."
    )

    LEFT_TURN_COMPLETE = (
        "Left turn complete. Continuing forward."
    )

    # ============================================================
    # MARKER 5 / DESTINATION
    # ============================================================

    MARKER5_DESTINATION = (
        "Destination command confirmed. Delivery point reached."
    )

    DESTINATION_MARKER_DETECTED = (
        "Destination marker detected."
    )

    CONFIRMING_DESTINATION = (
        "Confirming destination."
    )

    DESTINATION_REACHED = (
        "Delivery point reached."
    )

    DESTINATION_CONFIRMED = (
        "Destination confirmed. Delivery point reached."
    )

    DELIVERY_POINT_REACHED = (
        "Delivery point reached. Recipient verification is required."
    )

    DESTINATION_ACCEPTED = (
        "Destination command accepted."
    )

    STOPPING_NAVIGATION = (
        "Stopping normal navigation."
    )

    QR_COMPLETE = (
        "QR navigation is now complete."
    )

    PREPARING_AUTH = (
        "Preparing secure recipient verification."
    )

    # ============================================================
    # STOP
    # ============================================================

    STOP = (
        "Stop command received."
    )

    STOP_DETECTED = (
        "Stop command detected."
    )

    STOP_CONFIRMED = (
        "Stop command confirmed."
    )

    STOPPING_ROBOT = (
        "Stopping robot movement."
    )

    ROBOT_STOPPED = (
        "Robot movement stopped safely."
    )

    # ============================================================
    # UNKNOWN MARKER
    # ============================================================

    UNKNOWN_MARKER = (
        "Unknown QR marker detected. Ignoring the command."
    )

    # ============================================================
    # OBSTACLES
    # ============================================================

    OBSTACLE_DETECTED = (
        "Obstacle detected ahead."
    )

    CHECKING_OBSTACLE = (
        "Checking the path for a safe route."
    )

    AVOIDING_OBSTACLE = (
        "Obstacle detected. Beginning obstacle avoidance."
    )

    PATH_CLEAR = (
        "Path is clear. Resuming navigation."
    )

    OBSTACLE_CLEARED = (
        "Obstacle cleared. Continuing toward the destination."
    )

    STOPPING_FOR_OBSTACLE = (
        "Stopping temporarily for safety."
    )

    LEFT_PATH_CLEAR = (
        "Left path is clear."
    )

    RIGHT_PATH_CLEAR = (
        "Right path is clear."
    )

    BOTH_PATHS_BLOCKED = (
        "Both paths are blocked."
    )

    # ============================================================
    # CAMERA
    # ============================================================

    SWITCHING_CAMERA = (
        "Switching camera to face authentication mode."
    )

    FACE_CAMERA_READY = (
        "Face authentication camera ready."
    )

    # ============================================================
    # FACE AUTHENTICATION
    # ============================================================

    PLEASE_AUTHENTICATE = (
        "Recipient verification required. Please face the camera."
    )

    PLEASE_FACE_CAMERA = (
        "Please remain in front of the camera."
    )

    DELIVERY_LOCKED = (
        "The delivery will remain locked until your identity is verified."
    )

    STARTING_AUTH = (
        "Starting recipient authentication."
    )

    VERIFYING_RECIPIENT = (
        "Verifying recipient identity."
    )

    ANALYZING_FACE = (
        "Analyzing facial identity."
    )

    FACE_DETECTED = (
        "Face detected."
    )

    BEGINNING_VERIFICATION = (
        "Beginning identity verification."
    )

    MATCH_THRESHOLD = (
        "Identity match is above the required security threshold."
    )

    STRONG_MATCH = (
        "Strong identity match detected."
    )

    AUTH_COMPLETE = (
        "Face authentication process complete."
    )

    AUTH_CONFIRMATION = (
        "Waiting for authentication confirmation."
    )

    SECURITY_EVALUATING = (
        "Security controller is evaluating access."
    )

    AUTH_TIMEOUT = (
        "Authentication timed out. Access remains locked."
    )

    AUTH_SUCCESS = (
        "Identity verified. Access granted."
    )

    AUTH_FAILED = (
        "Identity verification failed. The delivery compartment remains locked."
    )

    LOCKOUT = (
        "Maximum attempts reached. AUTONEX is locking out further attempts."
    )

    ACCESS_GRANTED = (
        "Access granted."
    )

    # ============================================================
    # SECURITY / ACCESS
    # ============================================================

    IDENTITY_VERIFIED = (
        "Identity verified. Recipient authorized."
    )

    ACCESS_AUTHORIZED = (
        "Access authorized. Unlocking delivery compartment."
    )

    IDENTITY_SUCCESS = (
        "Identity verified successfully."
    )

    DELIVERY_ACCESS_AUTHORIZED = (
        "Delivery access authorized."
    )

    UNLOCKING_COMPARTMENT = (
        "Unlocking delivery compartment."
    )

    COMPARTMENT_OPEN = (
        "Compartment open."
    )

    COMPARTMENT_UNLOCKED = (
        "Compartment unlocked. Please collect your delivery."
    )

    COMPARTMENT_IS_UNLOCKED = (
        "Delivery compartment is now unlocked."
    )

    COLLECT_DELIVERY = (
        "Please collect your delivery."
    )

    AUTO_RELOCK = (
        "The compartment will be secured automatically."
    )

    AUTHORIZATION_COMPLETE = (
        "Delivery authorization completed."
    )

    DELIVERY_COMPLETE = (
        "Delivery completed successfully."
    )

    RECIPIENT_AUTHORIZED = (
        "Recipient access was authorized."
    )

    # ============================================================
    # ERROR
    # ============================================================

    SYSTEM_ERROR = (
        "A system error has occurred."
    )

    SAFE_STATE = (
        "AUTONEX is entering a safe state."
    )

    MISSION_ERROR = (
        "Mission ended because of a system error."
    )

    # ============================================================
    # SHUTDOWN
    # ============================================================

    SECURING_SYSTEM = (
        "Securing the delivery system."
    )

    STOPPING_OBSTACLE = (
        "Stopping obstacle detection."
    )

    SECURING_COMPARTMENT = (
        "Securing delivery compartment."
    )

    COMPARTMENT_SECURED = (
        "Delivery compartment secured."
    )

    CLOSING_CAMERA = (
        "Closing camera system."
    )

    MISSION_COMPLETE = (
        "Mission complete."
    )

    SHUTDOWN = (
        "AUTONEX shutting down. All systems secured. Goodbye."
    )

    # ============================================================
    # HEARTBEAT / EXTRA "AT EVERY STEP" NARRATION
    # ============================================================

    HEARTBEAT_MOVING = (
        "Still en route. All systems nominal."
    )

    HEARTBEAT_WAITING = (
        "Still waiting for the next marker."
    )


# ================================================================
# VOICE ANNOUNCER (async / real-time)
# ================================================================

class VoiceAnnouncer:
    """
    Real-time, non-blocking voice announcer.

    - `say()` / `speak()` enqueue text on a background worker thread
      and return almost immediately, so the caller (the robot's main
      control loop) is never held up waiting for a sentence to finish.
    - Messages are spoken strictly in the order they were queued.
    - `blocking=True` is honoured by waiting on a per-message event,
      for the few spots where you genuinely need to wait (e.g. right
      before the process exits).
    - `flush()` blocks until every currently queued message has been
      spoken - call this once at shutdown so AUTONEX doesn't get cut
      off mid-sentence when the program exits.
    """

    def __init__(
        self,
        rate=165,
        volume=0.9,
        enabled=True,
        max_queue=300,
    ):

        self.rate = rate
        self.volume = volume
        self.enabled = enabled
        self.max_queue = max_queue

        self._queue = queue.Queue(maxsize=max_queue)
        self._worker = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

        self._started = False

        self.last_spoken = None
        self.last_spoken_time = 0.0

    # ============================================================
    # START / WORKER
    # ============================================================

    def start(self):

        if not self.enabled:
            return

        with self._lock:

            if self._worker is not None and self._worker.is_alive():
                return

            self._stop_event.clear()

            self._worker = threading.Thread(
                target=self._worker_loop,
                name="AutonexVoiceWorker",
                daemon=True,
            )

            self._worker.start()

            self._started = True

        logger.info(
            "AUTONEX voice system started (real-time async mode)"
        )

    def _worker_loop(self):

        while not self._stop_event.is_set():

            try:

                text, done_event = self._queue.get(
                    timeout=0.2
                )

            except queue.Empty:

                continue

            # Sentinel used by stop() to unblock the worker cleanly.
            if text is None:

                self._queue.task_done()

                if done_event is not None:
                    done_event.set()

                break

            self._speak_now(text)

            self.last_spoken = text
            self.last_spoken_time = time.monotonic()

            if done_event is not None:
                done_event.set()

            self._queue.task_done()

    # ============================================================
    # ENGINE
    # ============================================================

    def _create_engine(self):

        engine = pyttsx3.init()

        engine.setProperty(
            "rate",
            self.rate
        )

        engine.setProperty(
            "volume",
            self.volume
        )

        voices = engine.getProperty(
            "voices"
        )

        selected_voice = None

        for voice in voices:

            name = str(
                getattr(
                    voice,
                    "name",
                    ""
                )
            ).lower()

            voice_id = str(
                getattr(
                    voice,
                    "id",
                    ""
                )
            ).lower()

            if (
                "zira" in name
                or "zira" in voice_id
            ):

                selected_voice = voice
                break

        if selected_voice is None and voices:
            selected_voice = voices[0]

        if selected_voice is not None:

            engine.setProperty(
                "voice",
                selected_voice.id
            )

        return engine

    def _speak_now(self, text):
        """
        Actually produces audio. Runs on the WORKER thread only, so
        it is free to block for as long as the sentence takes without
        affecting the robot's control loop.
        """

        logger.info(
            "AUTONEX VOICE: %s",
            text
        )

        engine = None

        try:

            engine = self._create_engine()

            engine.say(
                str(text)
            )

            engine.runAndWait()

        except Exception:

            logger.exception(
                "AUTONEX speech failed: %s",
                text
            )

        finally:

            if engine is not None:

                try:
                    engine.stop()
                except Exception:
                    pass

                del engine

    # ============================================================
    # PUBLIC API
    # ============================================================

    def say(
        self,
        text,
        blocking: bool = False,
    ):
        """
        Queue `text` to be spoken.

        blocking=False (default, and what you want for anything said
        during the main control loop): returns immediately, speech
        happens on the worker thread in the background - this is what
        makes announcements "real time" instead of freezing the robot.

        blocking=True: waits until this specific message has actually
        finished being spoken before returning. Use sparingly - only
        where you truly need to know the sentence has been said
        (e.g. the final goodbye before the process exits).
        """

        if not text:
            return

        if not self.enabled:
            logger.info(
                "AUTONEX VOICE (silent): %s",
                text
            )
            return

        if not self._started:
            self.start()

        done_event = (
            threading.Event()
            if blocking
            else None
        )

        try:

            self._queue.put_nowait(
                (text, done_event)
            )

        except queue.Full:

            logger.warning(
                "AUTONEX voice queue full - dropping: %s",
                text
            )

            return

        if blocking and done_event is not None:
            done_event.wait(timeout=20.0)

    def speak(
        self,
        text,
        blocking: bool = False,
    ):
        return self.say(
            text,
            blocking=blocking,
        )

    def flush(self, timeout: float = 15.0):
        """
        Block until every message currently queued has been spoken.
        Call this once, right before shutting the process down, so
        the last announcements aren't cut off mid-sentence.
        """

        if not self.enabled:
            return

        try:

            finished = threading.Event()

            def _waiter():
                self._queue.join()
                finished.set()

            waiter = threading.Thread(
                target=_waiter,
                daemon=True,
            )

            waiter.start()
            waiter.join(timeout=timeout)

        except Exception:

            logger.exception(
                "AUTONEX voice flush failed"
            )

    def stop(self):

        self._stop_event.set()

        try:
            self._queue.put_nowait((None, None))
        except queue.Full:
            pass

        if self._worker is not None:
            self._worker.join(timeout=3.0)

        self._started = False

        logger.info(
            "AUTONEX voice system stopped"
        )


# ================================================================
# DIRECT TEST
# ================================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s "
            "%(levelname)-8s "
            "%(name)-30s "
            "%(message)s"
        ),
        datefmt="%H:%M:%S",
    )

    print()
    print("=" * 60)
    print(" AUTONEX VOICE TEST (real-time / non-blocking)")
    print("=" * 60)
    print()

    voice = VoiceAnnouncer(
        rate=165,
        volume=0.9,
        enabled=True,
    )

    voice.start()

    # These all return almost instantly - notice the prints below
    # appear on screen well before AUTONEX finishes talking.
    voice.say("AUTONEX voice system test started.")
    voice.say("Start marker detected.")
    voice.say("Start command confirmed.")
    voice.say("Moving forward.")
    voice.say("Straight movement confirmed.")
    voice.say("Right turn command confirmed.")
    voice.say("Left turn command confirmed.")
    voice.say("Destination reached. Starting recipient authentication.")
    voice.say("Identity verified. Delivery compartment unlocked.")
    voice.say("Voice test completed successfully.", blocking=True)

    print("All messages queued/spoken - main thread was never blocked.")

    voice.flush()
    voice.stop()

    print()
    print("=" * 60)
    print(" VOICE TEST COMPLETE")
    print("=" * 60)