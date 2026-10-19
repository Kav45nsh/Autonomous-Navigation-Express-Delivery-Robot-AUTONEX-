// =====================================================================
// MotorController.cpp
// =====================================================================
#include "MotorController.h"
#include "config.h"
#include "Calibration.h"

MotorController Motors;

// ---------------------------------------------------------------
// SETUP
// ---------------------------------------------------------------
void MotorController::begin() {

    pinMode(PIN_LEFT_IN1, OUTPUT);
    pinMode(PIN_LEFT_IN2, OUTPUT);
    pinMode(PIN_RIGHT_IN3, OUTPUT);
    pinMode(PIN_RIGHT_IN4, OUTPUT);

    // NOTE: this uses the "classic" ESP32 Arduino core LEDC API
    // (ledcSetup + ledcAttachPin + ledcWrite(channel, ...)), which is
    // what most Arduino-ESP32 core 2.x installs (the common one for
    // college projects) provide. If your installed core is 3.x, that
    // API was replaced with ledcAttach(pin, freq, res) / ledcWrite(pin,
    // duty) - swap the two calls below accordingly and the rest of the
    // file does not need to change.
    ledcSetup(PWM_CHANNEL_LEFT, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
    ledcAttachPin(PIN_LEFT_ENA, PWM_CHANNEL_LEFT);

    ledcSetup(PWM_CHANNEL_RIGHT, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
    ledcAttachPin(PIN_RIGHT_ENB, PWM_CHANNEL_RIGHT);

    motorStop();
}

// ---------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------
uint8_t MotorController::clampPwm(int value) {
    if (value < 0) return 0;
    if (value > MAX_PWM) return MAX_PWM;
    return (uint8_t)value;
}

uint8_t MotorController::enforceMinEffective(uint8_t pwm) {
    // A nonzero-but-tiny PWM just makes the motor buzz without turning.
    // Either it's really zero (stop), or it must be at least the
    // minimum effective duty cycle.
    if (pwm == 0) return 0;
    if (pwm < MIN_EFFECTIVE_PWM) return MIN_EFFECTIVE_PWM;
    return pwm;
}

uint8_t MotorController::applyCorrection(uint8_t pwm, float correction) const {
    int corrected = (int)((float)pwm * correction);
    return enforceMinEffective(clampPwm(corrected));
}

// ---------------------------------------------------------------
// SINGLE MOTOR PRIMITIVES
// ---------------------------------------------------------------
void MotorController::leftMotorForward(uint8_t pwm) {
    bool fwd = !Cal.data().leftInverted;
    digitalWrite(PIN_LEFT_IN1, fwd ? HIGH : LOW);
    digitalWrite(PIN_LEFT_IN2, fwd ? LOW : HIGH);
    uint8_t corrected = applyCorrection(pwm, Cal.data().leftCorrection);
    ledcWrite(PWM_CHANNEL_LEFT, corrected);
    _lastLeft = corrected;
}

void MotorController::leftMotorBackward(uint8_t pwm) {
    bool fwd = !Cal.data().leftInverted;
    digitalWrite(PIN_LEFT_IN1, fwd ? LOW : HIGH);
    digitalWrite(PIN_LEFT_IN2, fwd ? HIGH : LOW);
    uint8_t corrected = applyCorrection(pwm, Cal.data().leftCorrection);
    ledcWrite(PWM_CHANNEL_LEFT, corrected);
    _lastLeft = -(int16_t)corrected;
}

void MotorController::leftMotorStop() {
    digitalWrite(PIN_LEFT_IN1, LOW);
    digitalWrite(PIN_LEFT_IN2, LOW);
    ledcWrite(PWM_CHANNEL_LEFT, 0);
    _lastLeft = 0;
}

void MotorController::rightMotorForward(uint8_t pwm) {
    bool fwd = !Cal.data().rightInverted;
    digitalWrite(PIN_RIGHT_IN3, fwd ? HIGH : LOW);
    digitalWrite(PIN_RIGHT_IN4, fwd ? LOW : HIGH);
    uint8_t corrected = applyCorrection(pwm, Cal.data().rightCorrection);
    ledcWrite(PWM_CHANNEL_RIGHT, corrected);
    _lastRight = corrected;
}

void MotorController::rightMotorBackward(uint8_t pwm) {
    bool fwd = !Cal.data().rightInverted;
    digitalWrite(PIN_RIGHT_IN3, fwd ? LOW : HIGH);
    digitalWrite(PIN_RIGHT_IN4, fwd ? HIGH : LOW);
    uint8_t corrected = applyCorrection(pwm, Cal.data().rightCorrection);
    ledcWrite(PWM_CHANNEL_RIGHT, corrected);
    _lastRight = -(int16_t)corrected;
}

void MotorController::rightMotorStop() {
    digitalWrite(PIN_RIGHT_IN3, LOW);
    digitalWrite(PIN_RIGHT_IN4, LOW);
    ledcWrite(PWM_CHANNEL_RIGHT, 0);
    _lastRight = 0;
}

// ---------------------------------------------------------------
// SIGNED HELPERS
// ---------------------------------------------------------------
void MotorController::setLeftPWM(int16_t pwm) {
    if (pwm > 0)      leftMotorForward((uint8_t)clampPwm(pwm));
    else if (pwm < 0) leftMotorBackward((uint8_t)clampPwm(-pwm));
    else              leftMotorStop();
}

void MotorController::setRightPWM(int16_t pwm) {
    if (pwm > 0)      rightMotorForward((uint8_t)clampPwm(pwm));
    else if (pwm < 0) rightMotorBackward((uint8_t)clampPwm(-pwm));
    else              rightMotorStop();
}

void MotorController::setMotorSpeed(int16_t leftPwm, int16_t rightPwm) {
    setLeftPWM(leftPwm);
    setRightPWM(rightPwm);
}

// ---------------------------------------------------------------
// WHOLE-ROBOT HELPERS
// ---------------------------------------------------------------
void MotorController::moveForward(uint8_t speed) {
    leftMotorForward(speed);
    rightMotorForward(speed);
}

void MotorController::moveBackward(uint8_t speed) {
    leftMotorBackward(speed);
    rightMotorBackward(speed);
}

void MotorController::turnLeft(uint8_t speed) {
#if TURN_MODE == TURN_MODE_IN_PLACE
    leftMotorBackward(speed);
    rightMotorForward(speed);
#else // TURN_MODE_PIVOT
    leftMotorStop();
    rightMotorForward(speed);
#endif
}

void MotorController::turnRight(uint8_t speed) {
#if TURN_MODE == TURN_MODE_IN_PLACE
    leftMotorForward(speed);
    rightMotorBackward(speed);
#else // TURN_MODE_PIVOT
    leftMotorForward(speed);
    rightMotorStop();
#endif
}

void MotorController::motorStop() {
    leftMotorStop();
    rightMotorStop();
}

void MotorController::motorBrake() {
    // Short dynamic-brake pulse: driving both direction pins of a
    // channel to the SAME level while the driver is enabled shorts the
    // motor winding through the H-bridge, which kills momentum fast.
    // This is a genuine hardware-settling delay (tens of ms), not a
    // control-flow delay, and is explicitly allowed by the design brief.
    digitalWrite(PIN_LEFT_IN1, HIGH);
    digitalWrite(PIN_LEFT_IN2, HIGH);
    digitalWrite(PIN_RIGHT_IN3, HIGH);
    digitalWrite(PIN_RIGHT_IN4, HIGH);
    ledcWrite(PWM_CHANNEL_LEFT, MAX_PWM);
    ledcWrite(PWM_CHANNEL_RIGHT, MAX_PWM);

    delay(BRAKE_PULSE_MS);

    motorStop();
}
