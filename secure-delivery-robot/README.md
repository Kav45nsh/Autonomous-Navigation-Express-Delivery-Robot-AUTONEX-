# Secure Delivery Robot

QR-waypoint navigation, obstacle avoidance, face-authenticated compartment
release. Develop entirely on a laptop webcam, deploy to a Raspberry Pi 4 by
changing one config value.

---

## The mission, end to end

```
IDLE → NAVIGATING → ARRIVING → AUTHENTICATING → DELIVERING → RETURNING → IDLE
          │              │             │              │
     follow QR      CAMERA MODE    face match     solenoid opens,
     markers,        SWITCHES      ≥ threshold    auto-relocks
     avoid people   640×480 →      + streak       after 5s
                    1280×720       + margin
```

---

## The camera mode switch

One physical camera, two jobs with opposite requirements.

| | NAVIGATION | FACE_AUTH |
|---|---|---|
| Resolution | 640×480 | 1280×720 |
| Frame rate | 30 fps | 15 fps |
| Why | markers are large, robot is moving, latency matters | robot is stationary, encoding quality needs pixels on the face |

`CameraManager` owns this. When the destination marker fires `ARRIVE`,
`main.py` enters the `ARRIVING` state and calls `camera.set_mode(FACE_AUTH)`.

Two details that will bite you if you build this yourself:

**A reconfigure is not free.** On picamera2 it is a real stop/configure/start
cycle, roughly 300–600 ms. Auto-exposure and white balance then need time to
re-converge at the new resolution, and frames captured during that window are
dark or washed out. They produce garbage face encodings. `CameraManager`
drains them for `MODE_SWITCH_SETTLE_SECONDS` before handing control back.
Do not set that to zero.

**`ARRIVING` is a named state on purpose.** The switch happens there rather
than at the top of `AUTHENTICATING`, so when the first few auth frames look
wrong, the log tells you immediately whether the mode switch was the cause.

Watch it live: `python -m camera.camera_test`, then press `n` / `f` / `i`.

---

## The unlock decision

Configured as you asked — 50% confidence opens the compartment:

```python
UNLOCK_CONFIDENCE_THRESHOLD = 0.50
```

Three guards sit on top of it. None of them makes life harder for the real
recipient, who clears all of them without noticing.

**Streak** (`AUTH_REQUIRED_STREAK = 4`) — the same person must win four
consecutive frames. A threshold alone can be cleared by a single lucky frame
during motion blur or an odd expression. Four in a row, about a quarter of a
second, cannot be luck.

**Margin** (`AUTH_MIN_MARGIN = 0.08`) — the best match must beat the best
*different* person by this much. Threshold asks "is this person similar
enough?" but never "similar compared to whom?" With several people enrolled,
a generic-looking face can sit just above 0.50 against three of them at once.
The margin rejects that as ambiguous instead of picking one arbitrarily.

**Liveness** (`REQUIRE_LIVENESS`, off by default) — see below.

### The limitation you should put in your report

A printed photo of the recipient unlocks this compartment. Every guard above
is defeated by it, because a photo genuinely *is* the right face. This is not
a flaw in the tuning; it is what face matching without anti-spoofing means.

`face_auth/liveness.py` ships a working motion-based approximation that
catches a static printout but not a video replay on a phone. The proper
version uses eye aspect ratio from facial landmarks to detect a real blink.
That is a strong extension, and naming the gap honestly is worth more marks
than pretending it isn't there.

Every unlock and every refusal is written to `logs/deliveries.jsonl` with the
recipient, confidence, threshold in force, and timestamp.

---

## Hardware abstraction

Nothing in this project touches hardware directly. Factories decide what you
get, based on `config/settings.py`, which auto-detects the platform by reading
`/proc/device-tree/model`.

| Concern | Laptop | Pi 4 | Interface |
|---|---|---|---|
| Camera | OpenCV webcam | picamera2 | `CameraSource` |
| Motors | simulated + pose estimate | gpiozero H-bridge | `MotorDriver` |
| Lock | console banner | GPIO + MOSFET | `LockDevice` |
| Range | scriptable fake | HC-SR04 | `RangeSensor` |
| Link | null | ESP32 serial | `Transport` |

Write against the ABCs in `core/interfaces.py`, never against `cv2` or
`gpiozero`. That is the whole migration strategy.

```bash
ROBOT_PLATFORM=pi python main.py       # force Pi backends
python main.py --simulate              # force all fakes, even on the Pi
```

---

## Quick start

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

python tools/check_hardware.py                          # diagnose first
python -m camera.camera_test                            # n/f/i to switch modes
python tools/generate_qr.py                             # print these
python -m qr_navigation.qr_detector
python -m face_auth.face_registration --name "Your Name" --samples 6
python -m face_auth.face_authentication
python main.py --simulate --telemetry                   # full mission
pytest -q                                               # 39 tests, no hardware
```

`SETUP.md` covers the Pi deployment. `HARDWARE.md` covers wiring —
**read it before connecting the solenoid.**

---

## Layout

```
secure-delivery-robot/
├── main.py                      mission orchestrator + THE MODE SWITCH
│
├── core/                        contracts and plumbing
│   ├── interfaces.py            CameraSource, MotorDriver, LockDevice, RangeSensor
│   ├── events.py                pub/sub bus — the seam for future features
│   ├── display.py               crash-safe cv2 GUI wrappers (headless-safe)
│   └── logging_setup.py
│
├── camera/
│   ├── camera_manager.py        ★ mode switching lives here
│   ├── backends/                webcam.py · picamera2_backend.py
│   └── camera_test.py           interactive mode-switch demo
│
├── qr_navigation/
│   ├── qr_detector.py           detection + steering error signal
│   ├── qr_commands.py           command vocabulary + dispatcher
│   ├── marker_handler.py        debounce, visit history, destination filter
│   └── route_map.py             graph + BFS route planning
│
├── face_auth/
│   ├── face_detector.py         where are the faces
│   ├── face_encoder.py          face → vector (dlib or LBPH)
│   ├── face_database.py         multi-sample enrollment store
│   ├── face_registration.py     enrollment CLI
│   ├── face_authentication.py   ★ threshold + streak + margin
│   └── liveness.py              anti-spoofing (extension point)
│
├── navigation/
│   ├── navigation.py            Navigator — QR following
│   ├── movement_controller.py   primitives + proportional steering
│   ├── robot_state.py           state machine with legal transitions
│   └── motors/                  simulated.py · gpio_motors.py
│
├── obstacle/
│   ├── obstacle_detector.py     distance → threat level, with hysteresis
│   ├── obstacle_avoidance.py    stop / wait / manoeuvre policy
│   └── sensors/                 simulated_range.py · ultrasonic.py
│
├── security/
│   ├── access_controller.py     ★ the ONLY thing that opens the lock
│   ├── solenoid_lock.py         timed unlock, watchdog, fail-secure
│   ├── audit_log.py             append-only delivery record (JSONL)
│   └── lock_backends/           simulated_lock.py · gpio_lock.py
│
├── voice/voice.py               threaded TTS + all phrases in one class
├── communication/
│   ├── esp32_serial.py          co-processor link
│   ├── protocol.py              ASCII line protocol with checksum
│   └── telemetry.py             event bus → JSONL / MQTT / WebSocket
│
├── config/settings.py           every tunable and platform switch
├── tools/                       generate_qr.py · check_hardware.py
├── data/                        faces, encodings, qr_codes (all gitignored)
├── logs/                        robot.log, deliveries.jsonl, telemetry.jsonl
└── tests/                       39 tests, zero hardware required
```

---

## Build order

Get 1–6 fully working on the laptop before buying a chassis. Debugging vision
code and motor wiring simultaneously is how these projects stall — and motor
brownouts produce symptoms that look exactly like software bugs.

1. Camera opens, modes switch cleanly
2. QR codes detected, correct commands resolved
3. Navigator steers correctly against simulated motors
4. Faces enroll and authenticate at sensible confidences
5. Simulated lock opens and relocks on a real match
6. `main.py --simulate` completes the whole mission
7. → then wire hardware, one subsystem at a time
