# Hardware

> **Read this before connecting anything to GPIO.** A Pi 4 GPIO pin sources
> about 16 mA at 3.3 V. A solenoid draws 300–600 mA at 12 V. Connecting one
> directly destroys the pin, and often the Pi.

---

## Bill of materials

| Part | Notes |
|---|---|
| Raspberry Pi 4 (2 GB+) | 4 GB is more comfortable if compiling dlib |
| Official 5V/3A USB-C PSU | underpowering causes freezes that mimic software bugs |
| Pi Camera Module 3, or USB webcam | CSI is better; USB works, set `CAMERA_BACKEND=webcam` |
| L298N or TB6612FNG driver | TB6612 is more efficient and runs cooler |
| 2× geared DC motors + wheels | |
| 12 V solenoid lock | check the current rating on the datasheet |
| IRLZ44N MOSFET **or** opto-isolated relay | logic-level gate matters — a plain IRF540 will not fully switch at 3.3 V |
| 1N4007 flyback diode | **not optional**, see below |
| HC-SR04 ultrasonic | |
| 1 kΩ + 2 kΩ resistors | voltage divider for HC-SR04 ECHO |
| 12 V battery pack | **separate from the Pi supply** |
| Common ground bus | |

---

## Power

Three rails, one shared ground:

```
5V USB-C  →  Pi
12V pack  →  motor driver  →  motors
12V pack  →  MOSFET        →  solenoid
              all grounds tied together
```

Never power motors or the solenoid from the Pi's 5V pins. A motor stall or a
solenoid inrush pulls the rail down, the Pi browns out and reboots mid-delivery,
and you will spend a weekend looking for the bug in your Python.

---

## Solenoid circuit

```
        +12V ────────┬──────────────┐
                     │              │
                  [solenoid]     [1N4007]   ← cathode (stripe) to +12V
                     │              │
                     ├──────────────┘
                     │
GPIO26 ──[1kΩ]──── GATE
                   IRLZ44N
              DRAIN │  SOURCE
                    └────┬────
                         │
        GND ─────────────┴──── (common with Pi GND)
```

**The flyback diode is not optional.** When the coil de-energises, its
collapsing magnetic field generates a reverse voltage spike of hundreds of
volts. The diode gives that spike a path back through the coil. Without it,
the spike reaches the MOSFET and then your GPIO pin. Stripe toward +12 V.

Prefer an opto-isolated relay module if you are not confident soldering — it
puts a physical air gap between 12 V and the Pi, and most modules include the
flyback diode. Slower and it clicks, which is fine for a lock.

### Fail-secure

`security/solenoid_lock.py` enforces this in three independent ways:

- a daemon timer relocks after `UNLOCK_DURATION_SECONDS`
- a watchdog force-releases at `MAX_CONTINUOUS_ENERGISE_S` — coils are rated
  for intermittent duty and will overheat if held
- `atexit` plus context-manager exit release on any crash path

A compartment stuck open is the worst outcome this project has. Choose a
solenoid that is **locked when unpowered**, so a dead battery means locked,
not open.

---

## Motor driver (L298N)

| L298N | Pi BCM | settings.py |
|---|---|---|
| IN1 | 17 | `PIN_LEFT_FORWARD` |
| IN2 | 18 | `PIN_LEFT_BACKWARD` |
| IN3 | 22 | `PIN_RIGHT_FORWARD` |
| IN4 | 23 | `PIN_RIGHT_BACKWARD` |
| ENA | 12 | `PIN_LEFT_ENABLE` (hardware PWM) |
| ENB | 13 | `PIN_RIGHT_ENABLE` (hardware PWM) |
| +12V | battery + | |
| GND | common | |

GPIO 12 and 13 are hardware-PWM capable. Software PWM on other pins jitters
under CPU load, which shows up as a robot that wanders while processing frames.

Remove the ENA/ENB jumpers or PWM does nothing.

---

## HC-SR04

ECHO outputs **5 V**. Divide it:

```
ECHO ──[1kΩ]──┬── GPIO25
              │
            [2kΩ]
              │
             GND
```

That gives 5 × 2/3 = 3.3 V. TRIG accepts 3.3 V directly on GPIO24.

Ultrasonic readings drop out on soft or angled surfaces. `ObstacleDetector`
takes a median of three samples and holds its previous state on a failed
reading — see `test_bad_reading_holds_state`.

---

## Calibration

Numbers that need tuning against your actual chassis, all in `settings.py`:

| Setting | How to find it |
|---|---|
| `TURN_DURATION` | time a 90° turn at `DEFAULT_SPEED`, adjust until square |
| `QR_ARRIVE_AREA` | run `qr_detector`, note the printed area at your stopping distance |
| `STEER_GAIN` | raise until it oscillates, then back off ~30% |
| `OBSTACLE_STOP_CM` | must exceed your braking distance at full speed |
| `DEFAULT_SPEED` | start at 0.4; faster means blurrier QR frames |
