// =====================================================================
// Calibration.h
//
// The values in config.h are compile-time STARTING POINTS. This module
// holds the same values as live, runtime-adjustable variables (loaded
// from flash/NVS if previously saved, otherwise the config.h defaults),
// so they can be tuned on the bench over Serial without re-flashing
// every time - then saved permanently once you're happy with them.
//
// MotorController / NavigationController / ObstacleAvoidance read the
// calibration-relevant values (motor correction/inversion, forward &
// turn speed, 90-degree turn timing, obstacle/side thresholds) from
// Cal.data() instead of the raw config.h macros, so a change here takes
// effect immediately, live, with the robot running.
// =====================================================================
#pragma once

#include <Arduino.h>
#include <Preferences.h>

struct CalibrationData {
    bool leftInverted;
    bool rightInverted;
    float leftCorrection;
    float rightCorrection;

    uint8_t forwardSpeed;
    uint8_t turnSpeed;

    uint16_t turnLeft90Ms;
    uint16_t turnRight90Ms;

    int obstacleStopDistance;
    int sideClearDistance;
};

class Calibration {
public:
    void begin();  // loads saved values from flash, or config.h defaults

    CalibrationData &data() { return _data; }

    bool isActive() const { return _active; }
    void enter();
    void exit();

    // Handles one calibration-mode command line (already trimmed and
    // upper-cased). Returns true if it recognized and handled it.
    // Supported:
    //   SHOW                  - print all current values
    //   SAVE                  - persist current values to flash
    //   RESET                 - restore config.h defaults (not saved until SAVE)
    //   EXIT                  - leave calibration mode
    //   SET <NAME> <VALUE>    - change one value, e.g. "SET LCORR 0.95"
    //     names: LINV RINV LCORR RCORR FSPEED TSPEED LTURN RTURN OBSTACLE SIDE
    bool handleCommand(const String &cmd);

    void printAll();
    void save();
    void resetToDefaults();

private:
    CalibrationData _data;
    bool _active = false;
    Preferences _prefs;

    void load();
    bool setByName(const String &name, const String &value);
};

extern Calibration Cal;
