"""
Single source of truth. Everything that differs between laptop and Pi 4,
and every tunable number, lives here and nowhere else.

Override anything at runtime with an environment variable or a .env file
(see .env.example) so you never have to edit this file on the robot itself.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _env(key: str, default):
    raw = os.getenv(key)
    if raw is None:
        return default
    if isinstance(default, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


# ══════════════════════════════════════════════════════════ paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FACES_DIR = DATA_DIR / "faces" / "known"
ENCODINGS_DIR = DATA_DIR / "encodings"
ENCODINGS_FILE = ENCODINGS_DIR / "face_encodings.pkl"
QR_CODES_DIR = DATA_DIR / "qr_codes"
LOG_DIR = BASE_DIR / "logs"
AUDIT_LOG = LOG_DIR / "deliveries.jsonl"

for _d in (FACES_DIR, ENCODINGS_DIR, QR_CODES_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════ platform
PLATFORM = _env("ROBOT_PLATFORM", "auto")          # auto | laptop | pi


def detect_platform() -> str:
    if PLATFORM in ("laptop", "pi"):
        return PLATFORM
    try:
        with open("/proc/device-tree/model") as f:
            if "raspberry pi" in f.read().lower():
                return "pi"
    except OSError:
        pass
    return "laptop"


IS_PI = detect_platform() == "pi"

CAMERA_BACKEND = _env("CAMERA_BACKEND", "picamera2" if IS_PI else "webcam")
MOTOR_BACKEND = _env("MOTOR_BACKEND", "gpio" if IS_PI else "simulated")
LOCK_BACKEND = _env("LOCK_BACKEND", "gpio" if IS_PI else "simulated")
RANGE_BACKEND = _env("RANGE_BACKEND", "ultrasonic" if IS_PI else "simulated")
VOICE_BACKEND = _env("VOICE_BACKEND", "pyttsx3")   # pyttsx3 | espeak | silent

HEADLESS = _env("HEADLESS", IS_PI)                 # no cv2.imshow on the robot
LOG_LEVEL = _env("LOG_LEVEL", "INFO")


# ══════════════════════════════════════════════════════════ camera modes
# The camera is reconfigured when the robot switches task. Navigation wants
# wide + fast + low-res. Face auth wants high-res detail and cares nothing
# about frame rate. See camera/camera_manager.py.
CAMERA_INDEX = _env("CAMERA_INDEX", 0)             # webcam only: 0 = built-in
FLIP_HORIZONTAL = _env("FLIP_HORIZONTAL", True)

CAMERA_MODES = {
    "NAVIGATION": {
        "width": 640, "height": 480, "fps": 30,
        "description": "Wide and fast. Reading QR waypoints while moving.",
    },
    "FACE_AUTH": {
        "width": 1280, "height": 720, "fps": 15,
        "description": "High detail. Recipient verification while stationary.",
    },
    "IDLE": {
        "width": 320, "height": 240, "fps": 10,
        "description": "Low power standby.",
    },
}
DEFAULT_CAMERA_MODE = "NAVIGATION"
MODE_SWITCH_SETTLE_SECONDS = 0.6   # let exposure/AWB re-converge after a switch


# ══════════════════════════════════════════════════════════ qr navigation
#
# QR codes are NAVIGATION EVENTS, not continuous motor commands. Once a
# marker is CONFIRMED, qr_navigation/marker_handler.py locks it so it cannot
# re-fire while it is still sitting in view, and navigation/navigation.py
# keeps doing whatever that command asked for (e.g. keeps driving straight)
# without needing to keep seeing the QR code.
#
QR_BACKEND = _env("QR_BACKEND", "opencv")          # opencv | pyzbar
QR_MIN_AREA = _env("QR_MIN_AREA", 1500)            # ignore tiny/noisy blobs

# Raw QR payload (uppercased) -> navigation command.
# This is looked up by qr_navigation/qr_commands.py. Add a new destination
# marker (bigger campus) by adding one more "MARKER n": "..." line here -
# nothing else in the codebase needs to change.
QR_COMMAND_MAP = {
    "MARKER 1": "START",
    "MARKER 2": "STRAIGHT",
    "MARKER 3": "RIGHT",
    "MARKER 4": "LEFT",
    "MARKER 5": "DESTINATION",
    "STOP": "STOP",          # a completely separate concept from DESTINATION
}

# ── confirmation / locking (the "real-world" QR behaviour you asked for) ──
QR_STABLE_FRAMES = _env("QR_STABLE_FRAMES", 3)
#   ^ a marker must be decoded this many consecutive frames before its
#     5-second confirmation timer is even allowed to start. Filters out a
#     single lucky/blurry decode.
QR_CONFIRMATION_TIME = _env("QR_CONFIRMATION_TIME", 5)
#   ^ THE 5 SECONDS. The marker must stay visible for this long, continuously,
#     before its command is executed.
QR_LOST_FRAMES = _env("QR_LOST_FRAMES", 8)
#   ^ once an accepted/being-tracked marker is missing for this many
#     consecutive frames, the handler resets so the SAME marker can be
#     confirmed again on a future pass.


# ══════════════════════════════════════════════════════════ motors
PIN_LEFT_FORWARD = 17
PIN_LEFT_BACKWARD = 18
PIN_RIGHT_FORWARD = 22
PIN_RIGHT_BACKWARD = 23
PIN_LEFT_ENABLE = 12         # hardware PWM capable
PIN_RIGHT_ENABLE = 13        # hardware PWM capable
PWM_FREQUENCY = 1000
DEFAULT_SPEED = _env("DEFAULT_SPEED", 0.55)
SLOW_SPEED = 0.30
STEER_GAIN = 0.8             # proportional steering strength
TURN_DURATION = 0.8          # seconds for a 90-degree-ish turn. Calibrate it.


# ══════════════════════════════════════════════════════════ obstacles
#
# THREE ultrasonic sensors: FRONT (is something in my path?), LEFT and RIGHT
# (is there room to slip past on that side?). See obstacle/obstacle_detector.py
# for how these numbers are turned into a decision, and
# obstacle/obstacle_avoidance.py for the "stop, check both sides, go around,
# come back" state machine.
PIN_ULTRASONIC_FRONT_TRIG = 24
PIN_ULTRASONIC_FRONT_ECHO = 25
PIN_ULTRASONIC_LEFT_TRIG = 5
PIN_ULTRASONIC_LEFT_ECHO = 6
PIN_ULTRASONIC_RIGHT_TRIG = 19
PIN_ULTRASONIC_RIGHT_ECHO = 20

FRONT_SAFE_DISTANCE_CM = _env("FRONT_SAFE_DISTANCE_CM", 30.0)
#   ^ front_distance < this  ->  OBSTACLE DETECTED, stop.
SIDE_SAFE_DISTANCE_CM = _env("SIDE_SAFE_DISTANCE_CM", 30.0)
#   ^ raw floor for "there is at least some room" before the width check below.

ROBOT_WIDTH_CM = _env("ROBOT_WIDTH_CM", 40.0)
SIDE_SAFETY_MARGIN_CM = _env("SIDE_SAFETY_MARGIN_CM", 15.0)
#   ^ A side sensor reading "50 cm" does NOT mean the robot fits - the robot
#     has a physical width. A side counts as clear only when:
#         side_distance_cm >= ROBOT_WIDTH_CM + SIDE_SAFETY_MARGIN_CM
#     Tune ROBOT_WIDTH_CM to your actual chassis once it is built, and widen
#     SIDE_SAFETY_MARGIN_CM if the robot still clips things.

OBSTACLE_RECHECK_INTERVAL = _env("OBSTACLE_RECHECK_INTERVAL", 0.5)
#   ^ how often (seconds) to re-measure both sides while BOTH are blocked.

AVOIDANCE_TURN_DURATION = _env("AVOIDANCE_TURN_DURATION", 0.3)
#   ^ small timed pivot used to *nudge* around an obstacle. Deliberately much
#     shorter than TURN_DURATION (the full 90-degree QR turn) - this is a
#     temporary deviation, not a route turn.
AVOIDANCE_FORWARD_DURATION = _env("AVOIDANCE_FORWARD_DURATION", 1.0)
#   ^ how long to drive forward, sideways-nudged, to actually clear the
#     obstacle's width before straightening back out.

RANGE_SAMPLE_COUNT = 3                                # median filter per read
RANGE_MAX_CM = 400.0


# ══════════════════════════════════════════════════════════ face auth
FACE_BACKEND = _env("FACE_BACKEND", "face_recognition")   # face_recognition | lbph
FACE_DETECTION_MODEL = "hog"       # hog = CPU friendly. cnn needs a GPU.
FACE_DOWNSCALE = 0.25              # process at 1/4 size -> ~4x faster

# ─── THE UNLOCK DECISION ──────────────────────────────────────────────
# confidence is 0.0-1.0, derived from encoding distance. You asked for 50%.
UNLOCK_CONFIDENCE_THRESHOLD = _env("UNLOCK_CONFIDENCE_THRESHOLD", 0.50)
#
# 0.70 alone is permissive. These three cheap guards do the real work:
AUTH_REQUIRED_STREAK = _env("AUTH_REQUIRED_STREAK", 4)
#   ^ N consecutive frames must name the SAME person. Kills lucky single frames.
AUTH_MIN_MARGIN = _env("AUTH_MIN_MARGIN", 0.08)
#   ^ best match must beat the runner-up by this much. Kills "everyone matches".
REQUIRE_LIVENESS = _env("REQUIRE_LIVENESS", False)
#   ^ demand a blink before unlocking. See face_auth/liveness.py.
# ──────────────────────────────────────────────────────────────────────

AUTH_TIMEOUT_SECONDS = _env("AUTH_TIMEOUT_SECONDS", 30)
AUTH_MAX_ATTEMPTS = 3              # then lock out and alert
AUTH_LOCKOUT_SECONDS = 60


# ══════════════════════════════════════════════════════════ solenoid lock
# A 12V solenoid CANNOT be driven from a GPIO pin. You need a MOSFET or relay
# module plus a flyback diode across the coil. See HARDWARE.md.
PIN_SOLENOID = 26
SOLENOID_ACTIVE_HIGH = True        # depends on your relay module
UNLOCK_DURATION_SECONDS = _env("UNLOCK_DURATION_SECONDS", 5.0)
MAX_CONTINUOUS_ENERGISE_S = 10.0   # hard ceiling: coils overheat and burn out
FAIL_SECURE = True                 # on crash/exit, lock rather than unlock


# ══════════════════════════════════════════════════════════ voice
VOICE_RATE = 165
VOICE_VOLUME = 0.9


# ══════════════════════════════════════════════════════════ esp32 link
ESP32_ENABLED = _env("ESP32_ENABLED", False)
ESP32_PORT = _env("ESP32_PORT", "/dev/ttyUSB0")   # Windows: "COM3"
ESP32_BAUD = _env("ESP32_BAUD", 115200)
ESP32_TIMEOUT = 1.0
ESP32_HEARTBEAT_SECONDS = 2.0

