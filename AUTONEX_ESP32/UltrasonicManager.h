// =====================================================================
// UltrasonicManager.h
//
// Handles all three HC-SR04 sensors. Every public getter returns a
// median-filtered distance in centimeters, or -1 if the reading could
// not be trusted (timeout, no echo, or too few valid samples). -1 must
// ALWAYS be treated as "unknown/unsafe", never as "clear" - the caller
// decides what conservative action to take.
// =====================================================================
#pragma once

#include <Arduino.h>

class UltrasonicManager {
public:
    void begin();

    long getFrontDistance();  // cm, or -1 if invalid -- median-of-N, use for decisions
    long getLeftDistance();   // cm, or -1 if invalid -- median-of-N, use for decisions
    long getRightDistance();  // cm, or -1 if invalid -- median-of-N, use for decisions

    // Single-ping "quick" reads - cheaper than the filtered versions, used
    // ONLY for the high-frequency safety interrupt checks while an
    // avoidance maneuver is already in progress (Section 14). Never use
    // these for the initial stop/choose-side decision - use the filtered
    // getters above for that.
    long getFrontQuick();
    long getLeftQuick();
    long getRightQuick();

private:
    long readRawOnce(uint8_t trigPin, uint8_t echoPin);
    long readFiltered(uint8_t trigPin, uint8_t echoPin);
    static int compareLong(const void *a, const void *b);
};

extern UltrasonicManager Ultrasonic;
