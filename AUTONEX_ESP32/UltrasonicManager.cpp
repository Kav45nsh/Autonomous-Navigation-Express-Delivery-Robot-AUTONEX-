// =====================================================================
// UltrasonicManager.cpp
// =====================================================================
#include "UltrasonicManager.h"
#include "config.h"
#include <stdlib.h>

UltrasonicManager Ultrasonic;

void UltrasonicManager::begin() {
    pinMode(PIN_FRONT_TRIG, OUTPUT);
    pinMode(PIN_FRONT_ECHO, INPUT);

    pinMode(PIN_LEFT_TRIG, OUTPUT);
    pinMode(PIN_LEFT_ECHO, INPUT);

    pinMode(PIN_RIGHT_TRIG, OUTPUT);
    pinMode(PIN_RIGHT_ECHO, INPUT);

    digitalWrite(PIN_FRONT_TRIG, LOW);
    digitalWrite(PIN_LEFT_TRIG, LOW);
    digitalWrite(PIN_RIGHT_TRIG, LOW);
}

// ---------------------------------------------------------------
// Single raw ping. Returns -1 on timeout / no echo / out-of-range.
// ---------------------------------------------------------------
long UltrasonicManager::readRawOnce(uint8_t trigPin, uint8_t echoPin) {

    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);

    unsigned long duration = pulseIn(echoPin, HIGH, ULTRASONIC_TIMEOUT_US);

    if (duration == 0) {
        // No echo returned within the timeout window - sensor
        // disconnected, out of range, or surface absorbed the pulse.
        return -1;
    }

    // Speed of sound ~343 m/s -> 0.0343 cm/us, divided by 2 for round trip.
    long distanceCm = (long)(duration * 0.0343f / 2.0f);

    if (distanceCm <= 0 || distanceCm > MAX_VALID_DISTANCE_CM) {
        return -1;
    }

    return distanceCm;
}

int UltrasonicManager::compareLong(const void *a, const void *b) {
    long la = *(const long *)a;
    long lb = *(const long *)b;
    if (la < lb) return -1;
    if (la > lb) return 1;
    return 0;
}

// ---------------------------------------------------------------
// Median-of-N filtered read. Rejects invalid samples up front; if
// too few of the N samples were valid, the whole reading is
// considered untrustworthy (returns -1) rather than guessing.
// ---------------------------------------------------------------
long UltrasonicManager::readFiltered(uint8_t trigPin, uint8_t echoPin) {

    long samples[ULTRASONIC_SAMPLE_COUNT];
    int validCount = 0;

    for (int i = 0; i < ULTRASONIC_SAMPLE_COUNT; i++) {

        long d = readRawOnce(trigPin, echoPin);

        if (d > 0) {
            samples[validCount++] = d;
        }

        if (i < ULTRASONIC_SAMPLE_COUNT - 1) {
            delay(ULTRASONIC_SAMPLE_GAP_MS);
        }
    }

    if (validCount < ULTRASONIC_MIN_VALID_SAMPLES) {
        // Not enough trustworthy samples - report "unknown", the
        // caller must treat this conservatively (never as "clear").
        return -1;
    }

    qsort(samples, validCount, sizeof(long), compareLong);

    return samples[validCount / 2]; // median
}

long UltrasonicManager::getFrontDistance() {
    return readFiltered(PIN_FRONT_TRIG, PIN_FRONT_ECHO);
}

long UltrasonicManager::getLeftDistance() {
    return readFiltered(PIN_LEFT_TRIG, PIN_LEFT_ECHO);
}

long UltrasonicManager::getRightDistance() {
    return readFiltered(PIN_RIGHT_TRIG, PIN_RIGHT_ECHO);
}

long UltrasonicManager::getFrontQuick() {
    return readRawOnce(PIN_FRONT_TRIG, PIN_FRONT_ECHO);
}

long UltrasonicManager::getLeftQuick() {
    return readRawOnce(PIN_LEFT_TRIG, PIN_LEFT_ECHO);
}

long UltrasonicManager::getRightQuick() {
    return readRawOnce(PIN_RIGHT_TRIG, PIN_RIGHT_ECHO);
}
