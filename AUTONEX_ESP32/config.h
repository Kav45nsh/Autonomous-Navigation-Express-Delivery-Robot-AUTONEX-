// =====================================================================
// config.h
//
// EVERY tunable value in the AUTONEX motor/obstacle-avoidance firmware
// lives in this one file. Nothing below is guaranteed to be correct for
// your physical robot - these are sane starting points. Use the
// built-in CALIBRATION mode (see Calibration.h) to tune them on the
// bench, then update the numbers here (or let Calibration persist them
// to flash - see Calibration.cpp).
//
// No existing ESP32 project/pin map was provided for this build, so the
// pin numbers below are a fresh, clearly-labeled assignment for a
// standard ESP32 DevKit + L298N + 3x HC-SR04. If your physical wiring
// is already different, just change the numbers in this one place -
// nothing else in the codebase needs to change.
// =====================================================================
#pragma once

// #####################################################################
// #  1. L298N MOTOR DRIVER PINS
// #####################################################################

#define PIN_LEFT_ENA   13   // Left motor speed (PWM)
#define PIN_LEFT_IN1   32   // Left motor direction A  (NOT GPIO12: boot-strapping pin)
#define PIN_LEFT_IN2   33   // Left motor direction B

#define PIN_RIGHT_ENB  27   // Right motor speed (PWM)
#define PIN_RIGHT_IN3  26   // Right motor direction A
#define PIN_RIGHT_IN4  25   // Right motor direction B

// ESP32 LEDC (hardware PWM) configuration for motor speed control.
#define PWM_CHANNEL_LEFT    0
#define PWM_CHANNEL_RIGHT   1
#define PWM_FREQUENCY_HZ    2000     // audible-free, plenty for DC brushed motors
#define PWM_RESOLUTION_BITS 8        // 0-255 duty range

// Reverse either of these to "true" if a motor spins the wrong way once wired.
#define LEFT_MOTOR_INVERTED   false
#define RIGHT_MOTOR_INVERTED  false

// Independent per-side correction factor (0.5 - 1.0 typical). Real gear
// motors never match perfectly - use this to make the robot track
// straight instead of curving. Tune with the "AUTO"/calibration test mode.
#define LEFT_MOTOR_CORRECTION   1.00f
#define RIGHT_MOTOR_CORRECTION  1.00f

// #####################################################################
// #  2. ULTRASONIC SENSOR PINS (HC-SR04 x3)
// #####################################################################
//
// IMPORTANT WIRING NOTE:
// HC-SR04 ECHO pins output 5V logic. ESP32 GPIOs are 3.3V logic and are
// NOT 5V tolerant - feeding ECHO directly into the ESP32 can damage the
// pin over time. Put a resistor divider (e.g. 1kΩ from ECHO to the GPIO,
// 2kΩ from that GPIO node to GND) or a proper logic-level shifter on
// EVERY echo line before it reaches the ESP32. TRIG pins are fine
// driven directly from a 3.3V GPIO.

#define PIN_FRONT_TRIG  5
#define PIN_FRONT_ECHO  18

#define PIN_LEFT_TRIG   19
#define PIN_LEFT_ECHO   21

#define PIN_RIGHT_TRIG  22
#define PIN_RIGHT_ECHO  23

// #####################################################################
// #  3. COMMUNICATION
// #####################################################################

// Raspberry Pi <-> ESP32 link. Kept on hardware UART2 so the USB
// Serial port stays free for debugging/test-mode the whole time.
// Wiring: Pi TXD (GPIO14/pin8)  -> ESP32 GPIO16 (RX2)
//         Pi RXD (GPIO15/pin10) <- ESP32 GPIO17 (TX2)
//         Pi GND                -- ESP32 GND        (common ground, required)
// Both the Pi GPIO header and the ESP32 run 3.3V logic, so a direct
// connection is fine - no level shifter needed for this particular link.
#define PI_SERIAL        Serial2
#define PI_RX_PIN        16
#define PI_TX_PIN        17
#define PI_BAUD_RATE     115200

// USB serial - used for debug logging AND the standalone test/
// calibration mode described in Sections 28-29.
#define DEBUG_BAUD_RATE  115200

// #####################################################################
// #  4. MOTOR SPEEDS (PWM duty, 0-255)
// #####################################################################

#define MAX_PWM               255
#define MIN_EFFECTIVE_PWM      60   // below this most small DC gear motors just buzz/stall

#define FORWARD_SPEED         190   // normal cruising speed
#define TURN_SPEED            170   // speed used for 90-degree turns
#define SLOW_SPEED            120   // used for the deceleration window near end of a turn
#define OBSTACLE_SPEED        140   // speed used while bypassing an obstacle

// #####################################################################
// #  5. DIFFERENTIAL DRIVE / TURN CONFIGURATION
// #####################################################################

// TURN_MODE_IN_PLACE: both wheels spin, opposite directions (tighter turn,
//                     needs a good caster wheel / low-friction floor).
// TURN_MODE_PIVOT:    one wheel stops, the other drives (gentler on gearing,
//                     wider turning radius).
#define TURN_MODE_IN_PLACE  0
#define TURN_MODE_PIVOT     1
#define TURN_MODE           TURN_MODE_IN_PLACE

// STARTING POINTS ONLY - see the calibration walkthrough in the README
// section of this reply. These WILL need to be re-measured on your
// actual robot; do not trust them as-is.
#define TURN_LEFT_90_MS         700
#define TURN_RIGHT_90_MS        730
#define TURN_DECEL_WINDOW_MS    120   // slow to SLOW_SPEED for the last N ms of a turn
#define TURN_SETTLE_TIME_MS     150   // pause after stopping, before reporting TURN_COMPLETE
#define BRAKE_AFTER_TURN        true
#define BRAKE_PULSE_MS           40   // short dynamic-brake pulse (hardware settling only)

// #####################################################################
// #  6. ULTRASONIC SAMPLING / FILTERING
// #####################################################################

#define ULTRASONIC_SAMPLE_COUNT       5      // median-of-5
#define ULTRASONIC_MIN_VALID_SAMPLES  3      // need at least this many valid readings of N
#define ULTRASONIC_SAMPLE_GAP_MS      12     // gap between samples (avoids cross-talk / echo overlap)
#define ULTRASONIC_TIMEOUT_US         25000  // ~4.3 m round-trip ceiling
#define MAX_VALID_DISTANCE_CM         400    // HC-SR04 practical max range

// #####################################################################
// #  7. OBSTACLE THRESHOLDS (centimeters)
// #####################################################################

#define OBSTACLE_STOP_DISTANCE    30   // FRONT <= this -> stop and start avoidance
#define SAFE_DISTANCE             40   // FRONT >  this -> considered clear to cruise
#define SIDE_CLEAR_DISTANCE       35   // a side must exceed this to be considered usable
#define CRITICAL_DISTANCE         15   // <= this on ANY sensor -> emergency stop
#define SIDE_SELECTION_MARGIN      8   // one side must beat the other by this much to be preferred

#define OBSTACLE_CLEAR_CONFIRMATIONS  3   // consecutive clear samples required before declaring "cleared"

// How often (ms) the FRONT sensor is polled while cruising normally.
// A full median-of-N read takes a few tens of ms (see Section 6 timing),
// so this is rate-limited rather than read every single loop() pass -
// otherwise sensor sampling would dominate the loop and slow down
// command/watchdog handling. For higher-rate sensing later, swap in an
// interrupt/echo-timer based ultrasonic library (e.g. NewPing) behind
// the same UltrasonicManager interface - nothing else would need to change.
#define FRONT_POLL_INTERVAL_MS    80

// A sensor that returns invalid readings this many times in a row is
// considered failed, not just noisy -> SENSOR_ERROR + emergency stop
// (Section 26), instead of endlessly retrying obstacle avoidance
// against a phantom reading.
#define SENSOR_ERROR_CONSECUTIVE_LIMIT   8

// How long to wait after stopping for an obstacle before trusting the
// robot is physically stationary and reading the side sensors.
#define OBSTACLE_SETTLE_MS        150

// When both sides are within SIDE_SELECTION_MARGIN of each other,
// which way does the robot default to? true = RIGHT, false = LEFT.
#define AVOID_TIE_BREAK_RIGHT     true

// #####################################################################
// #  8. OBSTACLE AVOIDANCE MANEUVER TIMING (ms)
// #####################################################################

#define AVOID_TURN_MS             450   // initial turn toward the chosen side
#define AVOID_FORWARD_MS          900   // creep alongside the obstacle
#define AVOID_RETURN_TURN_MS      450   // turn back toward the original heading
#define AVOID_STATE_POLL_MS       40    // how often the avoidance FSM re-checks sensors mid-maneuver

#define BLOCKED_RECHECK_INTERVAL_MS  1000
#define BLOCKED_REPORT_TIMEOUT_MS    15000  // notify Pi with OBSTACLE_BLOCKED after being stuck this long

// #####################################################################
// #  9. SAFETY / WATCHDOG
// #####################################################################

#define COMMAND_TIMEOUT_MS   2000   // no valid command from the Pi within this window -> STOP

// #####################################################################
// #  10. LOGGING
// #####################################################################

#define LOG_INTERVAL_MS   400   // minimum spacing between repeated periodic status/sensor logs
