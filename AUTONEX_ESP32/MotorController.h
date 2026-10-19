// =====================================================================
// MotorController.h
//
// Clean abstraction over the L298N + 2x DC gear motors. This class
// knows nothing about navigation, obstacles or communication - it only
// ever converts a requested speed/direction into GPIO + PWM signals.
// Per-motor inversion and correction factors (config.h) are applied
// here, in exactly one place.
// =====================================================================
#pragma once

#include <Arduino.h>

class MotorController {
public:
    void begin();

    // ---- Single-motor primitives ----
    void leftMotorForward(uint8_t pwm);
    void leftMotorBackward(uint8_t pwm);
    void leftMotorStop();

    void rightMotorForward(uint8_t pwm);
    void rightMotorBackward(uint8_t pwm);
    void rightMotorStop();

    // ---- Signed helpers: positive = forward, negative = backward, 0 = stop ----
    void setLeftPWM(int16_t pwm);
    void setRightPWM(int16_t pwm);
    void setMotorSpeed(int16_t leftPwm, int16_t rightPwm);

    // ---- Whole-robot helpers ----
    void moveForward(uint8_t speed);
    void moveBackward(uint8_t speed);

    // Continuous turning primitives - caller (NavigationController /
    // ObstacleAvoidance) is responsible for timing / stopping these.
    void turnLeft(uint8_t speed);
    void turnRight(uint8_t speed);

    void motorStop();     // coast to a stop (driver outputs disabled)
    void motorBrake();    // short dynamic-brake pulse, then coast

    // Last commanded raw PWM values, for logging/telemetry only.
    int16_t lastLeftPwm() const { return _lastLeft; }
    int16_t lastRightPwm() const { return _lastRight; }

private:
    int16_t _lastLeft = 0;
    int16_t _lastRight = 0;

    uint8_t applyCorrection(uint8_t pwm, float correction) const;
    static uint8_t clampPwm(int value);
    static uint8_t enforceMinEffective(uint8_t pwm);
};

extern MotorController Motors;
