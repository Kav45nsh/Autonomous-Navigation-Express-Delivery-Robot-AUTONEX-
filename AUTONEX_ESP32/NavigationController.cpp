// =====================================================================
// NavigationController.cpp
// =====================================================================
#include "NavigationController.h"
#include "config.h"
#include "MotorController.h"
#include "ObstacleAvoidance.h"
#include "SafetyController.h"
#include "Communication.h"
#include "Calibration.h"

NavigationController Navigation;

void NavigationController::begin() {
    _currentCommand = NavCommand::STOP;
    _previousCommand = NavCommand::NONE;
    _originalNavigationCommand = NavCommand::STOP;
    _lastSafeDirection = NavCommand::STOP;
    _lastCommandTime = millis();
    _turnPhase = TurnPhase::NONE;
}

// ---------------------------------------------------------------
// COMMAND ENTRY POINT (Section 20-22)
// ---------------------------------------------------------------
void NavigationController::handleCommand(NavCommand cmd) {

    _lastCommandTime = millis();
    Safety.feedWatchdog();

    // ---- Highest priority: EMERGENCY_STOP always wins ----
    if (cmd == NavCommand::EMERGENCY_STOP) {
        Motors.motorStop();
        Obstacle.cancel();
        Safety.triggerEmergency("PI_EMERGENCY_STOP");
        _previousCommand = _currentCommand;
        _currentCommand = NavCommand::EMERGENCY_STOP;
        _turnPhase = TurnPhase::NONE;
        Comm.sendStatus(F("STOPPED"));
        return;
    }

    // ---- RESUME clears a latched emergency / watchdog trip ----
    if (cmd == NavCommand::RESUME) {
        Safety.clearEmergency();
        _previousCommand = _currentCommand;
        _currentCommand = NavCommand::STOP;
        _originalNavigationCommand = NavCommand::STOP;
        Comm.sendStatus(F("READY"));
        return;
    }

    // ---- STOP cancels ANY in-progress avoidance/turn immediately (Section 25) ----
    if (cmd == NavCommand::STOP) {
        Obstacle.cancel();
        Motors.motorStop();
        _turnPhase = TurnPhase::NONE;
        _previousCommand = _currentCommand;
        _currentCommand = NavCommand::STOP;
        _originalNavigationCommand = NavCommand::STOP;
        Comm.sendStatus(F("STOPPED"));
        return;
    }

    // ---- STATUS is a query, it does not change the active command ----
    if (cmd == NavCommand::STATUS) {
        sendFullStatus();
        return;
    }

    // ---- Genuine movement/turn commands ----
    _previousCommand = _currentCommand;
    _currentCommand = cmd;
    _originalNavigationCommand = cmd;   // this IS the route - only another
                                        // explicit Pi command may change it
    _lastSafeDirection = cmd;

    switch (cmd) {

        case NavCommand::FORWARD:
            Obstacle.reset();
            Comm.sendStatus(F("MOVING_FORWARD"));
            break;

        case NavCommand::BACKWARD:
            Obstacle.reset();
            Comm.sendStatus(F("MOVING_BACKWARD"));
            break;

        case NavCommand::LEFT:
        case NavCommand::RIGHT:
            Obstacle.reset();
            break;

        case NavCommand::TURN_LEFT_90:
            Obstacle.reset();
            startTurn(true);
            break;

        case NavCommand::TURN_RIGHT_90:
            Obstacle.reset();
            startTurn(false);
            break;

        default:
            break;
    }
}

void NavigationController::manualDrive(int16_t left, int16_t right) {
    Safety.feedWatchdog();
    Obstacle.cancel();
    _turnPhase = TurnPhase::NONE;
    _previousCommand = _currentCommand;
    _currentCommand = NavCommand::MANUAL;
    _manualLeft = left;
    _manualRight = right;
}

bool NavigationController::isMotionCommanded() const {
    return _currentCommand != NavCommand::STOP &&
           _currentCommand != NavCommand::NONE &&
           _currentCommand != NavCommand::EMERGENCY_STOP;
}

void NavigationController::startTurn(bool isLeft) {
    _turnIsLeft = isLeft;
    _turnPhase = TurnPhase::SPINNING;
    _turnPhaseStart = millis();
    Comm.log(F("MOTOR"), isLeft ? F("TURN LEFT 90 START") : F("TURN RIGHT 90 START"));
}

// ---------------------------------------------------------------
// PER-LOOP DRIVE (Section 21 priority order lives here)
// ---------------------------------------------------------------
void NavigationController::update() {

    // ---- Priority 1: emergency stop overrides everything, no exceptions ----
    if (Safety.emergencyActive()) {
        Motors.motorStop();
        Comm.logThrottled(F("SAFETY"), String("EMERGENCY ACTIVE (") + Safety.emergencyReason() + ")");
        return;
    }

    // ---- Communication watchdog tripped without an explicit EMERGENCY_STOP ----
    if (Safety.isCommandTimedOut() && _currentCommand != NavCommand::STOP) {
        Motors.motorStop();
        _currentCommand = NavCommand::STOP;
        Comm.log(F("SAFETY"), F("COMMAND TIMEOUT - MOTORS STOPPED"));
        Comm.sendStatus(F("STOPPED"));
    }

    switch (_currentCommand) {

        case NavCommand::FORWARD: {
            // Priority 2: obstacle safety. ObstacleAvoidance drives the
            // motors itself in every state except NORMAL_MOVEMENT.
            ObstacleState s = Obstacle.update();
            if (s == ObstacleState::NORMAL_MOVEMENT) {
                Motors.moveForward(Cal.data().forwardSpeed);
            }
            break;
        }

        case NavCommand::BACKWARD:
            // No rear ultrasonic sensor exists on this build - reversing
            // is straight, unguarded motion. Keep BACKWARD moves short
            // and Pi-supervised; add a rear sensor before relying on this
            // for anything but short, deliberate reversing.
            Motors.moveBackward(Cal.data().forwardSpeed);
            break;

        case NavCommand::LEFT:
            Motors.turnLeft(Cal.data().turnSpeed);
            break;

        case NavCommand::RIGHT:
            Motors.turnRight(Cal.data().turnSpeed);
            break;

        case NavCommand::MANUAL:
            Motors.setMotorSpeed(_manualLeft, _manualRight);
            break;

        case NavCommand::TURN_LEFT_90:
        case NavCommand::TURN_RIGHT_90:
            updateTurn();
            break;

        case NavCommand::STOP:
        case NavCommand::EMERGENCY_STOP:
        case NavCommand::NONE:
        default:
            Motors.motorStop();
            break;
    }
}

// ---------------------------------------------------------------
// CALIBRATED, NON-BLOCKING 90-DEGREE TURN (Sections 17-18)
//
// Phases: SPINNING (full Cal.data().turnSpeed) -> DECELERATING (SLOW_SPEED for
// the last TURN_DECEL_WINDOW_MS, to fight overshoot) -> brake/stop ->
// SETTLING (short pause) -> report TURN_COMPLETE and go idle, awaiting
// the Pi's next command (per Section 24: Pi sends TURN_*_90, then a
// separate FORWARD).
// ---------------------------------------------------------------
void NavigationController::updateTurn() {

    unsigned long elapsed = millis() - _turnPhaseStart;
    unsigned long totalMs = _turnIsLeft ? Cal.data().turnLeft90Ms : Cal.data().turnRight90Ms;

    switch (_turnPhase) {

        case TurnPhase::SPINNING:
            if (elapsed < (totalMs > TURN_DECEL_WINDOW_MS ? totalMs - TURN_DECEL_WINDOW_MS : 0)) {
                if (_turnIsLeft) Motors.turnLeft(Cal.data().turnSpeed);
                else             Motors.turnRight(Cal.data().turnSpeed);
            } else {
                _turnPhase = TurnPhase::DECELERATING;
            }
            break;

        case TurnPhase::DECELERATING:
            if (elapsed < totalMs) {
                if (_turnIsLeft) Motors.turnLeft(SLOW_SPEED);
                else             Motors.turnRight(SLOW_SPEED);
            } else {
                if (BRAKE_AFTER_TURN) Motors.motorBrake();
                else                  Motors.motorStop();
                _turnPhase = TurnPhase::SETTLING;
                _turnPhaseStart = millis();
            }
            break;

        case TurnPhase::SETTLING:
            Motors.motorStop();
            if (millis() - _turnPhaseStart >= TURN_SETTLE_TIME_MS) {
                Comm.log(F("MOTOR"), _turnIsLeft ? F("LEFT TURN COMPLETE") : F("RIGHT TURN COMPLETE"));
                Comm.sendStatus(F("TURN_COMPLETE"));

                _turnPhase = TurnPhase::NONE;
                _previousCommand = _currentCommand;
                _currentCommand = NavCommand::STOP; // idle; Pi sends FORWARD next
            }
            break;

        case TurnPhase::NONE:
        default:
            Motors.motorStop();
            break;
    }
}

// ---------------------------------------------------------------
// STATUS QUERY (Section 20 - "STATUS" command)
// ---------------------------------------------------------------
void NavigationController::sendFullStatus() {
    Comm.sendStatus(F("STATUS_REPORT"));
    Comm.log(F("STATUS"),
        String("CMD=") + navCommandToString(_currentCommand) +
        " PREV=" + navCommandToString(_previousCommand) +
        " ROUTE=" + navCommandToString(_originalNavigationCommand) +
        " OBSTACLE=" + obstacleStateToString(Obstacle.getState()) +
        " L_PWM=" + String(Motors.lastLeftPwm()) +
        " R_PWM=" + String(Motors.lastRightPwm()) +
        " EMERGENCY=" + String(Safety.emergencyActive() ? "YES" : "NO"));
}
