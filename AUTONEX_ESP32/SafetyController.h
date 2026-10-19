// =====================================================================
// SafetyController.h
//
// Owns the communication watchdog and the global emergency-stop latch.
// This is intentionally the highest-priority module: NavigationController
// checks it FIRST, every loop, before doing anything else.
// =====================================================================
#pragma once

#include <Arduino.h>

class SafetyController {
public:
    void begin();

    // Call whenever a valid, well-formed command is received from the
    // Pi. Resets the communication watchdog timer.
    void feedWatchdog();

    // Must be called every loop() iteration. The comms watchdog is only
    // enforced while motion is commanded (idle + silent Pi is normal).
    void update(bool motionCommanded);

    bool isCommandTimedOut() const { return _commandTimedOut; }

    // Any of: comms timeout, critical obstacle distance, explicit
    // EMERGENCY_STOP command, sensor failure condition, software fault.
    bool emergencyActive() const { return _emergencyActive; }
    const char *emergencyReason() const { return _reason; }

    void triggerEmergency(const char *reason);

    // Only an explicit resume/clear from the Pi (or test mode) should
    // call this - never auto-clear silently.
    void clearEmergency();

private:
    unsigned long _lastCommandTime = 0;
    bool _commandTimedOut = false;
    bool _emergencyActive = false;
    char _reason[32] = "";
};

extern SafetyController Safety;
