// =====================================================================
// SafetyController.cpp
// =====================================================================
#include "SafetyController.h"
#include "config.h"
#include <string.h>

SafetyController Safety;

void SafetyController::begin() {
    _lastCommandTime = millis();
    _commandTimedOut = false;
    _emergencyActive = false;
    _reason[0] = '\0';
}

void SafetyController::feedWatchdog() {
    _lastCommandTime = millis();
    if (_commandTimedOut) {
        _commandTimedOut = false;
    }
}

void SafetyController::update(bool motionCommanded) {
    unsigned long now = millis();

    if (motionCommanded && !_commandTimedOut && (now - _lastCommandTime > COMMAND_TIMEOUT_MS)) {
        _commandTimedOut = true;
        triggerEmergency("COMM_TIMEOUT");
    }
}

void SafetyController::triggerEmergency(const char *reason) {
    _emergencyActive = true;
    strncpy(_reason, reason, sizeof(_reason) - 1);
    _reason[sizeof(_reason) - 1] = '\0';
}

void SafetyController::clearEmergency() {
    _emergencyActive = false;
    _reason[0] = '\0';
    // Clearing emergency also counts as "we heard from the Pi again".
    feedWatchdog();
}
