# Future scope

Extension points already built into the structure, roughly by effort. Each
names the file to open, so none of these needs a redesign.

---

## Small — a weekend each

**Proper PID steering** → `navigation/movement_controller.py::steer()`
Currently proportional only. Add integral to correct steady drift on sloped
floors, derivative to damp the oscillation that appears at higher speeds. Log
the error signal and plot it in your report; a before/after chart is strong
evidence.

**Battery monitoring** → new `sensors/battery.py` implementing `RangeSensor`-
style interface, INA219 over I²C. Announce low battery, refuse new deliveries
below a threshold, return to dock.

**Delivery confirmation** → `security/access_controller.py`
Add a photo capture at the moment of unlock, stored alongside the audit entry.
Proof of who collected the package.

**Multi-recipient packages** → `config/settings.py`
`TARGET_DESTINATION` is a single value. Make it a list of (destination,
authorised_names) pairs and loop the mission.

---

## Medium — a few weeks

**Real liveness detection** → `face_auth/liveness.py`
The single highest-value improvement. Replace the motion approximation with
eye aspect ratio from `face_recognition.face_landmarks`: compute EAR per frame,
detect the characteristic dip-and-recover of a blink, require one before
unlocking. Defeats the printed-photo attack that currently works.

**Route planning in use** → `qr_navigation/route_map.py`
The graph and BFS are implemented and tested but not yet wired into
`Navigator`. Use `next_expected()` to detect wrong turns, and announce
"unexpected waypoint, recalculating" instead of continuing cheerfully.

**ESP32 co-processor** → `communication/esp32_serial.py`
Protocol and transport are done; `ESP32_ENABLED=False` by default. Move motor
PWM and ultrasonic polling to the ESP32 for hard real-time timing Linux cannot
promise, and so a Python crash cannot leave the motors running.

**Live dashboard** → `communication/telemetry.py`
The event bus already publishes everything. JSONL logging works today. Add
`paho-mqtt` (about 20 lines, sketched in comments) or flask-socketio for a
browser view of state, camera mode, and battery.

**Obstacle avoidance that actually avoids** → `obstacle/obstacle_avoidance.py`
Current policy is stop-wait-sidestep, which is correct but timid. Multiple
sensors give a left/right decision. A cheap 2D LIDAR gives real local planning.

---

## Large — final-year project scale

**SLAM instead of QR markers**
QR waypoints need a prepared environment. RTAB-Map or ORB-SLAM3 on the Pi 4 is
tight but feasible at low resolution; offloading to a laptop over WiFi is more
realistic. This is a project in itself.

**ROS 2 migration**
The interfaces in `core/interfaces.py` map cleanly onto ROS nodes: camera
publisher, QR detector, navigation, obstacle monitor, security service. The
abstraction work is already done.

**On-device face recognition acceleration**
A Coral USB Accelerator or Hailo-8L HAT moves recognition from ~2 fps to
real-time on the Pi 4. Requires a TFLite/ONNX model swap — add a third backend
in `face_auth/face_encoder.py` alongside `face_recognition` and `lbph`.

**Fleet coordination**
Multiple robots, a central dispatcher, shared map, collision avoidance at
junctions. MQTT from the telemetry work is the natural transport.

---

## Report material already in the repo

- `logs/deliveries.jsonl` — every unlock and refusal with confidence and
  threshold. Two lines of pandas gives you an accuracy table.
- `logs/telemetry.jsonl` (`--telemetry`) — full event trace per run.
- `StateMachine.timeline()` — the actual state sequence, good for a figure.
- `tests/` — 39 tests. "We wrote unit tests for the security-critical path"
  is a genuine differentiator in an undergraduate project.

## Evaluation worth running

1. **FAR/FRR sweep.** Vary `UNLOCK_CONFIDENCE_THRESHOLD` from 0.3 to 0.8 and
   plot false accepts against false rejects. This turns "we picked 50%" into
   "we chose 50% because the curves cross near there for our enrollment set",
   which is a much stronger sentence.
2. **Photo-attack success rate.** Try the printed-photo attack 20 times, with
   and without liveness. Report the number honestly.
3. **Mode-switch latency.** Time `set_mode()` on the Pi and justify your
   settling value with data.
4. **Navigation accuracy.** Stopping-distance variance across 20 approaches.
