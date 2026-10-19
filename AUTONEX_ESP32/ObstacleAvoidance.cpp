// =====================================================================
// ObstacleAvoidance.cpp
// =====================================================================
#include "ObstacleAvoidance.h"
#include "config.h"
#include "MotorController.h"
#include "UltrasonicManager.h"
#include "SafetyController.h"
#include "Communication.h"
#include "Calibration.h"

ObstacleAvoidance Obstacle;

void ObstacleAvoidance::begin() {
    _state = ObstacleState::NORMAL_MOVEMENT;
    _stateEnteredTime = millis();
    _lastFrontPollTime = 0;
    _lastSafetyPollTime = 0;
    _leftDistance = -1;
    _rightDistance = -1;
    _chosenSide = AvoidSide::NONE;
    _clearConfirmations = 0;
    _consecutiveFrontInvalid = 0;
    _blockedSince = 0;
    _blockedTimeoutReported = false;
}

void ObstacleAvoidance::reset() {
    // Not currently driving forward - nothing to avoid. Clear transient
    // counters but there is no need to touch the motors here; whatever
    // called us (NavigationController) owns the motors in this case.
    if (_state != ObstacleState::NORMAL_MOVEMENT) {
        _state = ObstacleState::NORMAL_MOVEMENT;
        _stateEnteredTime = millis();
    }
    _clearConfirmations = 0;
    _consecutiveFrontInvalid = 0;
    _chosenSide = AvoidSide::NONE;
}

void ObstacleAvoidance::cancel() {
    // Hard abort - used when the Pi sends STOP mid-maneuver (Section 25).
    Motors.motorStop();
    Comm.log(F("AVOID"), F("CANCELLED BY STOP COMMAND"));
    _state = ObstacleState::NORMAL_MOVEMENT;
    _stateEnteredTime = millis();
    _clearConfirmations = 0;
    _consecutiveFrontInvalid = 0;
    _chosenSide = AvoidSide::NONE;
    _blockedTimeoutReported = false;
}

void ObstacleAvoidance::enterState(ObstacleState s) {
    _state = s;
    _stateEnteredTime = millis();
}

// ---------------------------------------------------------------
// MAIN ENTRY POINT
// ---------------------------------------------------------------
ObstacleState ObstacleAvoidance::update() {

    switch (_state) {

        case ObstacleState::NORMAL_MOVEMENT:
            driveNormalMovementCheck();
            break;

        case ObstacleState::OBSTACLE_DETECTED:
            driveObstacleDetected();
            break;

        case ObstacleState::CHECKING_LEFT:
            driveCheckingLeft();
            break;

        case ObstacleState::CHECKING_RIGHT:
            driveCheckingRight();
            break;

        case ObstacleState::CHOOSING_PATH:
            driveChoosingPath();
            break;

        case ObstacleState::AVOIDING_LEFT:
            if (!safetyInterruptCheck()) driveAvoiding(true);
            break;

        case ObstacleState::AVOIDING_RIGHT:
            if (!safetyInterruptCheck()) driveAvoiding(false);
            break;

        case ObstacleState::PASSING_OBSTACLE:
            if (!safetyInterruptCheck()) drivePassingObstacle();
            break;

        case ObstacleState::REACQUIRING_DIRECTION:
            if (!safetyInterruptCheck()) driveReacquiring();
            break;

        case ObstacleState::RESUMING_MOVEMENT:
            driveResuming();
            break;

        case ObstacleState::BLOCKED:
            driveBlocked();
            break;

        case ObstacleState::EMERGENCY_STOP:
            // Stays here until SafetyController's emergency is cleared
            // externally (main.ino handles this on a valid resume).
            Motors.motorStop();
            if (!Safety.emergencyActive()) {
                enterState(ObstacleState::NORMAL_MOVEMENT);
            }
            break;
    }

    return _state;
}

// ---------------------------------------------------------------
// NORMAL_MOVEMENT: rate-limited front polling
// ---------------------------------------------------------------
void ObstacleAvoidance::driveNormalMovementCheck() {

    unsigned long now = millis();

    if (now - _lastFrontPollTime < FRONT_POLL_INTERVAL_MS) {
        return; // too soon, keep cruising (caller drives motors forward)
    }
    _lastFrontPollTime = now;

    long front = Ultrasonic.getFrontDistance();

    if (front > 0) {
        Comm.logThrottled(F("ULTRASONIC"), "F=" + String(front) + "cm");
    } else {
        Comm.logThrottled(F("ULTRASONIC"), F("F=ERR"));
    }

    // ---- Critical distance: no time for the full avoidance sequence ----
    if (front > 0 && front <= CRITICAL_DISTANCE) {
        Motors.motorBrake();
        Safety.triggerEmergency("CRITICAL_FRONT");
        Comm.sendStatus(F("EMERGENCY_STOP"));
        Comm.log(F("SAFETY"), F("CRITICAL FRONT DISTANCE"));
        enterState(ObstacleState::EMERGENCY_STOP);
        return;
    }

    // ---- Invalid reading: never assume clear (Section 6/26) ----
    if (front < 0) {
        _consecutiveFrontInvalid++;

        if (_consecutiveFrontInvalid >= SENSOR_ERROR_CONSECUTIVE_LIMIT) {
            Motors.motorStop();
            Safety.triggerEmergency("FRONT_SENSOR_FAIL");
            Comm.sendStatus(F("SENSOR_ERROR"));
            Comm.log(F("SAFETY"), F("FRONT SENSOR FAILED - TOO MANY INVALID READS"));
            enterState(ObstacleState::EMERGENCY_STOP);
            return;
        }

        // Occasional invalid reading: be conservative, treat exactly
        // like an obstacle rather than assuming the path is open.
        beginObstacleSequence();
        return;
    }

    _consecutiveFrontInvalid = 0;

    if (front <= Cal.data().obstacleStopDistance) {
        beginObstacleSequence();
    }
}

void ObstacleAvoidance::beginObstacleSequence() {
    Motors.motorStop();
    Comm.log(F("OBSTACLE"), F("STOPPING"));
    Comm.sendStatus(F("OBSTACLE_DETECTED"));
    enterState(ObstacleState::OBSTACLE_DETECTED);
}

// ---------------------------------------------------------------
// OBSTACLE_DETECTED: wait for the robot to become physically stationary
// ---------------------------------------------------------------
void ObstacleAvoidance::driveObstacleDetected() {
    Motors.motorStop(); // keep re-asserting stop while we settle
    if (millis() - _stateEnteredTime >= OBSTACLE_SETTLE_MS) {
        Comm.sendStatus(F("CHECKING_LEFT"));
        enterState(ObstacleState::CHECKING_LEFT);
    }
}

// ---------------------------------------------------------------
// CHECKING_LEFT / CHECKING_RIGHT: filtered reads of each side
// ---------------------------------------------------------------
void ObstacleAvoidance::driveCheckingLeft() {
    _leftDistance = Ultrasonic.getLeftDistance();
    Comm.log(F("OBSTACLE"), "LEFT=" + (_leftDistance > 0 ? String(_leftDistance) + "cm" : String("ERR")));
    Comm.sendStatus(F("CHECKING_RIGHT"));
    enterState(ObstacleState::CHECKING_RIGHT);
}

void ObstacleAvoidance::driveCheckingRight() {
    _rightDistance = Ultrasonic.getRightDistance();
    Comm.log(F("OBSTACLE"), "RIGHT=" + (_rightDistance > 0 ? String(_rightDistance) + "cm" : String("ERR")));
    enterState(ObstacleState::CHOOSING_PATH);
}

// ---------------------------------------------------------------
// CHOOSING_PATH: compare both sides with a safety margin (Section 11)
// ---------------------------------------------------------------
void ObstacleAvoidance::chooseSide() {

    bool leftUsable  = (_leftDistance  > 0 && _leftDistance  >= Cal.data().sideClearDistance);
    bool rightUsable = (_rightDistance > 0 && _rightDistance >= Cal.data().sideClearDistance);

    if (!leftUsable && !rightUsable) {
        _chosenSide = AvoidSide::NONE;
        return;
    }
    if (!leftUsable) {
        _chosenSide = AvoidSide::RIGHT;
        return;
    }
    if (!rightUsable) {
        _chosenSide = AvoidSide::LEFT;
        return;
    }

    // Both usable - only prefer one if it clearly beats the other.
    if (_leftDistance > _rightDistance + SIDE_SELECTION_MARGIN) {
        _chosenSide = AvoidSide::LEFT;
    } else if (_rightDistance > _leftDistance + SIDE_SELECTION_MARGIN) {
        _chosenSide = AvoidSide::RIGHT;
    } else {
        _chosenSide = AVOID_TIE_BREAK_RIGHT ? AvoidSide::RIGHT : AvoidSide::LEFT;
    }
}

void ObstacleAvoidance::driveChoosingPath() {

    chooseSide();

    Comm.log(F("OBSTACLE"), "LEFT=" + (_leftDistance > 0 ? String(_leftDistance) : String("ERR"))
                          + "cm RIGHT=" + (_rightDistance > 0 ? String(_rightDistance) : String("ERR")) + "cm");

    if (_chosenSide == AvoidSide::NONE) {
        Motors.motorStop();
        Comm.sendStatus(F("BLOCKED"));
        Comm.log(F("SAFETY"), F("BLOCKED"));
        _blockedSince = millis();
        _blockedTimeoutReported = false;
        enterState(ObstacleState::BLOCKED);
        return;
    }

    if (_chosenSide == AvoidSide::LEFT) {
        Comm.log(F("OBSTACLE"), F("CHOSEN=LEFT"));
        Comm.sendStatus(F("AVOIDING_LEFT"));
        Comm.log(F("AVOID"), F("TURN LEFT"));
        enterState(ObstacleState::AVOIDING_LEFT);
    } else {
        Comm.log(F("OBSTACLE"), F("CHOSEN=RIGHT"));
        Comm.sendStatus(F("AVOIDING_RIGHT"));
        Comm.log(F("AVOID"), F("TURN RIGHT"));
        enterState(ObstacleState::AVOIDING_RIGHT);
    }

    _lastSafetyPollTime = millis();
}

// ---------------------------------------------------------------
// CONTINUOUS SAFETY MONITORING DURING A MANEUVER (Section 14)
// ---------------------------------------------------------------
bool ObstacleAvoidance::safetyInterruptCheck() {

    unsigned long now = millis();
    if (now - _lastSafetyPollTime < AVOID_STATE_POLL_MS) {
        return false; // not time to poll yet, current maneuver continues
    }
    _lastSafetyPollTime = now;

    long front = Ultrasonic.getFrontQuick();

    if (front > 0 && front <= CRITICAL_DISTANCE) {
        Motors.motorBrake();
        Safety.triggerEmergency("CRITICAL_DURING_AVOID");
        Comm.sendStatus(F("EMERGENCY_STOP"));
        Comm.log(F("SAFETY"), F("CRITICAL DISTANCE DURING AVOIDANCE"));
        enterState(ObstacleState::EMERGENCY_STOP);
        return true;
    }

    if (front > 0 && front <= Cal.data().obstacleStopDistance) {
        // A new/different obstacle appeared mid-maneuver (Test 14) -
        // stop and reassess from scratch rather than blindly continuing.
        Motors.motorStop();
        Comm.log(F("AVOID"), F("NEW OBSTACLE DURING MANEUVER - REASSESSING"));
        Comm.sendStatus(F("OBSTACLE_DETECTED"));
        enterState(ObstacleState::OBSTACLE_DETECTED);
        return true;
    }

    if (_state == ObstacleState::AVOIDING_LEFT) {
        long left = Ultrasonic.getLeftQuick();
        if (left > 0 && left <= CRITICAL_DISTANCE) {
            Motors.motorStop();
            Comm.log(F("AVOID"), F("LEFT SIDE BLOCKED MID-TURN - REASSESSING"));
            Comm.sendStatus(F("OBSTACLE_DETECTED"));
            enterState(ObstacleState::OBSTACLE_DETECTED);
            return true;
        }
    } else if (_state == ObstacleState::AVOIDING_RIGHT) {
        long right = Ultrasonic.getRightQuick();
        if (right > 0 && right <= CRITICAL_DISTANCE) {
            Motors.motorStop();
            Comm.log(F("AVOID"), F("RIGHT SIDE BLOCKED MID-TURN - REASSESSING"));
            Comm.sendStatus(F("OBSTACLE_DETECTED"));
            enterState(ObstacleState::OBSTACLE_DETECTED);
            return true;
        }
    }

    return false;
}

// ---------------------------------------------------------------
// AVOIDING_LEFT / AVOIDING_RIGHT: initial turn toward the chosen side
// ---------------------------------------------------------------
void ObstacleAvoidance::driveAvoiding(bool isLeft) {

    unsigned long elapsed = millis() - _stateEnteredTime;

    if (elapsed < AVOID_TURN_MS) {
        if (isLeft) Motors.turnLeft(OBSTACLE_SPEED);
        else        Motors.turnRight(OBSTACLE_SPEED);
        return;
    }

    Motors.motorStop();
    Comm.log(F("AVOID"), F("PASSING OBSTACLE"));
    enterState(ObstacleState::PASSING_OBSTACLE);
    _lastSafetyPollTime = millis();
}

// ---------------------------------------------------------------
// PASSING_OBSTACLE: creep forward alongside the obstacle
// ---------------------------------------------------------------
void ObstacleAvoidance::drivePassingObstacle() {

    unsigned long elapsed = millis() - _stateEnteredTime;

    if (elapsed < AVOID_FORWARD_MS) {
        Motors.moveForward(OBSTACLE_SPEED);
        return;
    }

    Motors.motorStop();
    Comm.log(F("AVOID"), F("FRONT CLEAR"));
    Comm.log(F("AVOID"), F("REACQUIRING ORIGINAL DIRECTION"));
    Comm.sendStatus(F("REACQUIRING_DIRECTION"));
    enterState(ObstacleState::REACQUIRING_DIRECTION);
    _lastSafetyPollTime = millis();
}

// ---------------------------------------------------------------
// REACQUIRING_DIRECTION: turn back the opposite way, toward the
// original heading that NavigationController still holds unchanged.
// ---------------------------------------------------------------
void ObstacleAvoidance::driveReacquiring() {

    unsigned long elapsed = millis() - _stateEnteredTime;
    bool wasLeftAvoid = (_chosenSide == AvoidSide::LEFT);

    if (elapsed < AVOID_RETURN_TURN_MS) {
        // Turn back the OPPOSITE way from the initial avoidance turn.
        if (wasLeftAvoid) Motors.turnRight(OBSTACLE_SPEED);
        else              Motors.turnLeft(OBSTACLE_SPEED);
        return;
    }

    Motors.motorStop();
    _clearConfirmations = 0;
    enterState(ObstacleState::RESUMING_MOVEMENT);
}

// ---------------------------------------------------------------
// RESUMING_MOVEMENT: require several consecutive clear FRONT readings
// before fully handing back control (Section 16 - avoid oscillation).
// ---------------------------------------------------------------
void ObstacleAvoidance::driveResuming() {

    Motors.motorStop();

    long front = Ultrasonic.getFrontDistance();

    if (front > 0 && front > SAFE_DISTANCE) {
        _clearConfirmations++;
    } else {
        _clearConfirmations = 0; // any non-clear reading resets the streak
    }

    if (_clearConfirmations >= OBSTACLE_CLEAR_CONFIRMATIONS) {
        Comm.log(F("AVOID"), F("RESUMED FORWARD"));
        Comm.sendStatus(F("OBSTACLE_CLEARED"));
        Comm.sendStatus(F("RESUMED_FORWARD"));
        _chosenSide = AvoidSide::NONE;
        _consecutiveFrontInvalid = 0;
        enterState(ObstacleState::NORMAL_MOVEMENT);
    }
}

// ---------------------------------------------------------------
// BLOCKED: front, left and right all unusable. Wait and recheck
// periodically rather than thrashing between turns (Section 15).
// ---------------------------------------------------------------
void ObstacleAvoidance::driveBlocked() {

    Motors.motorStop();

    unsigned long now = millis();

    if (!_blockedTimeoutReported && (now - _blockedSince >= BLOCKED_REPORT_TIMEOUT_MS)) {
        Comm.sendStatus(F("OBSTACLE_BLOCKED"));
        Comm.log(F("SAFETY"), F("BLOCKED TIMEOUT - NOTIFYING RASPBERRY PI"));
        _blockedTimeoutReported = true;
    }

    if (now - _lastFrontPollTime < BLOCKED_RECHECK_INTERVAL_MS) {
        return;
    }
    _lastFrontPollTime = now;

    long front = Ultrasonic.getFrontDistance();

    if (front < 0 || front <= Cal.data().obstacleStopDistance) {
        // Still blocked ahead too - no point checking sides yet.
        return;
    }

    // Front opened up - recheck both sides and try choosing a path again.
    Comm.sendStatus(F("CHECKING_LEFT"));
    enterState(ObstacleState::CHECKING_LEFT);
}
