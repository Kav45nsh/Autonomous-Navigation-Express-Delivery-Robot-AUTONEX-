# AUTONEX ESP32 – Motor + Obstacle Avoidance Firmware

The Pi decides the **route**. The ESP32 executes it and keeps the robot safe.
Obstacle avoidance is a *temporary local behaviour*: `ObstacleAvoidance` never
touches the command the Pi issued (`NavigationController` keeps
`current_command` / `original_navigation_command`), so the route can't be corrupted.

## Files (all in one sketch folder `AUTONEX_ESP32/`)
| File | Role |
|---|---|
| `AUTONEX_ESP32.ino` | setup/loop, Pi + USB command parsing, test mode |
| `config.h` | pins, speeds, thresholds, timing (defaults) |
| `AutonexTypes.h` | shared enums |
| `MotorController` | L298N + PWM abstraction, inversion/correction, brake |
| `UltrasonicManager` | 3× HC-SR04, median-of-5, invalid = -1 (never "clear") |
| `ObstacleAvoidance` | 12-state non-blocking avoidance FSM |
| `NavigationController` | command memory, priority, calibrated 90° turns |
| `SafetyController` | comms watchdog + emergency latch |
| `Communication` | ALL Serial/Serial2 I/O |
| `Calibration` | live tuning over serial, saved to flash |

No existing ESP32 sketch was provided, so **pins are new**. Change them only in `config.h`.

## Wiring (ESP32 DevKit)
**L298N** (remove ENA/ENB jumpers so PWM works; motor supply on 12V/VS, ESP32 GND tied to L298N GND):
ENA→GPIO13, IN1→GPIO32, IN2→GPIO33, ENB→GPIO27, IN3→GPIO26, IN4→GPIO25.
(GPIO12 was deliberately avoided – it is a boot-strapping pin.)

**HC-SR04** (VCC 5V, GND common):
Front TRIG 5 / ECHO 18 · Left TRIG 19 / ECHO 21 · Right TRIG 22 / ECHO 23.
⚠ **ECHO is 5 V.** Put a divider on each ECHO line (1 kΩ in series to the GPIO, 2 kΩ from GPIO to GND) or a level shifter. TRIG is fine direct.

**Raspberry Pi link (UART2, 3.3 V both sides):**
Pi TXD (GPIO14, pin 8) → ESP32 GPIO16 · Pi RXD (GPIO15, pin 10) ← ESP32 GPIO17 · GND ↔ GND.
Enable the Pi serial port (`raspi-config` → Interface → Serial: login shell **off**, hardware **on**); device is `/dev/serial0`.

## Upload
1. Arduino IDE → Boards Manager → install **esp32 by Espressif (core 2.0.x)**.
2. Open `AUTONEX_ESP32.ino` (folder name must equal the sketch name).
3. Board: *ESP32 Dev Module*, select COM port, Upload. Serial Monitor **115200**, line ending **Newline**.
4. Core 3.x users: replace `ledcSetup/ledcAttachPin/ledcWrite(channel)` in `MotorController.cpp` with `ledcAttach(pin,freq,res)` / `ledcWrite(pin,duty)`.

> ⚠ I could only syntax-check this against stubs, not on hardware. First tests: **wheels lifted off the ground**.

## Test sequence (USB Serial Monitor; type `HELP`)
1. `ML` left motor forward → `S`. Wrong direction? `CAL` → `SET LINV 1`.
2. `MR` right motor → `S`. Wrong way? `SET RINV 1`.
3. `F` both forward → `S`. Drifts? adjust `SET LCORR 0.95` (slow the faster side).
4. `B` both backward → `S`.
5. `TL` then 6. `TR`: see calibration below.
7–9. `SENSORS` with a hand at known distances in front/left/right; compare to a ruler. `ERR` = invalid (unplugged/no echo).
10. Put a box ~60 cm ahead, on the floor, then `AUTO`. Expect: `OBSTACLE_DETECTED → CHECKING_LEFT → CHECKING_RIGHT → CHOSEN=… → AVOIDING_… → PASSING → REACQUIRING → OBSTACLE_CLEARED → RESUMED_FORWARD`. `STATUS` should still show `ROUTE=FORWARD` the whole time.
11/12. Block the left (or right) side with a board → it must choose the other.
13. Block both sides → `BLOCKED`; `OBSTACLE_BLOCKED` is sent after 15 s; unblock → it retries.
14. Walk a hand in front mid-maneuver → immediate stop + reassessment.
15. `WDOG` (enforce watchdog), `F`, then send nothing → stops after 2 s with `COMM_TIMEOUT`. Send `RESUME` to clear.
16. During an avoidance maneuver send `S` → stops instantly, avoidance cancelled.

## Calibrating turns
`CAL`, then repeat: `TL`, look at the result, `SET LTURN <ms>` (more ms = more rotation). Same for `TR`/`SET RTURN`. Mark the floor with tape for a true 90°. Also tune `SET TSPEED`. When happy: `SAVE` (stored in flash, survives power-off), `EXIT`.
Other tunables: `FSPEED, LCORR, RCORR, OBSTACLE (stop cm), SIDE (side-clear cm)`. `SHOW` prints all; `RESET` restores `config.h` defaults.
Timed turns drift with battery level and floor; for accuracy later, add an MPU6050 or wheel encoders inside `NavigationController::updateTurn()` (interfaces are isolated for that).
Avoidance maneuver timing (`AVOID_TURN_MS`, `AVOID_FORWARD_MS`, `AVOID_RETURN_TURN_MS`) is in `config.h` – tune so the robot clears your typical obstacle width.

## Raspberry Pi integration (pyserial)
```python
import serial, time, threading
esp = serial.Serial("/dev/serial0", 115200, timeout=0.1)
def send(cmd): esp.write((cmd + "\n").encode())

# Heartbeat: while moving, the ESP32 stops if it hears nothing for 2 s.
def heartbeat():
    while True:
        send("STATUS"); time.sleep(0.5)
threading.Thread(target=heartbeat, daemon=True).start()

# QR events (Pi translates markers, ESP32 never sees QR):
# MARKER 1 -> nothing yet; MARKER 2 -> FORWARD
send("FORWARD")
# MARKER 3: send("TURN_RIGHT_90"); wait for "TURN_COMPLETE"; send("FORWARD")
# MARKER 4: send("TURN_LEFT_90");  wait for "TURN_COMPLETE"; send("FORWARD")
# MARKER 5: send("STOP")
line = esp.readline().decode().strip()   # READY, MOVING_FORWARD, OBSTACLE_DETECTED,
                                          # BLOCKED, OBSTACLE_BLOCKED, SENSOR_ERROR, ...
```
Good hooks for your voice module: map `OBSTACLE_DETECTED`, `AVOIDING_LEFT/RIGHT`, `OBSTACLE_CLEARED`, `BLOCKED`, `TURN_COMPLETE` straight to `_say(...)`.
After `EMERGENCY_STOP`, `SENSOR_ERROR` or a watchdog trip the robot stays stopped until the Pi sends `RESUME`.

## Known limits (be honest in your report)
- No rear sensor: `BACKWARD` is unguarded.
- Ultrasonic sampling is a few tens of ms per filtered read (bounded `delay`s), polled every 80 ms; use an interrupt-based library for faster sensing.
- Bypass is time-based (open-loop) – it returns to roughly, not exactly, the original line. Encoders/IMU are the upgrade path.
- HC-SR04 can miss soft/angled surfaces; keep thresholds conservative.
