// =====================================================================
// ObstacleAvoidance.h
//
// Local, temporary obstacle-avoidance behavior (Sections 9-16). This
// module NEVER touches NavigationController's "original_navigation_command"
// - it only ever drives the motors itself while active, then hands
// control back once NORMAL_MOVEMENT is restored. That separation is
// what guarantees "obstacle avoidance is temporary, the route is
// permanent" (Section 12).
//
// Usage from NavigationController, every loop while the commanded
// heading is FORWARD:
//
//      ObstacleState s = Obstacle.update();
//      if (s == ObstacleState::NORMAL_MOVEMENT) {
//          Motors.moveForward(FORWARD_SPEED);   // caller drives
//      }
//      // any other state: ObstacleAvoidance has already driven the
//      // motors itself for this tick.
//
// When the commanded heading is anything other than FORWARD (STOP,
// turning, backward, etc.), call Obstacle.reset() instead of update().
// If a STOP is received while avoidance is active, call Obstacle.cancel().
// =====================================================================
#pragma once

#include <Arduino.h>
#include "AutonexTypes.h"

class ObstacleAvoidance {
public:
    void begin();

    // Call every loop while the robot is commanded FORWARD. Returns the
    // current state; NORMAL_MOVEMENT means "nothing to do, drive
    // forward yourself" - anything else means this module already
    // controlled the motors for this tick.
    ObstacleState update();

    // Call every loop while the robot is NOT commanded FORWARD (idle,
    // stopped, turning, reversing). Clears counters, does not touch
    // motors (caller isn't driving through this module in that case).
    void reset();

    // Immediately abort any in-progress avoidance and stop. Used when
    // the Pi sends STOP while avoidance is active (Section 25).
    void cancel();

    ObstacleState getState() const { return _state; }
    bool isBlocked() const { return _state == ObstacleState::BLOCKED; }
    bool isNormal() const { return _state == ObstacleState::NORMAL_MOVEMENT; }

private:
    ObstacleState _state = ObstacleState::NORMAL_MOVEMENT;

    unsigned long _stateEnteredTime = 0;
    unsigned long _lastFrontPollTime = 0;
    unsigned long _lastSafetyPollTime = 0;

    long _leftDistance = -1;
    long _rightDistance = -1;

    AvoidSide _chosenSide = AvoidSide::NONE;
    int _clearConfirmations = 0;
    int _consecutiveFrontInvalid = 0;

    unsigned long _blockedSince = 0;
    bool _blockedTimeoutReported = false;

    void enterState(ObstacleState s);
    void beginObstacleSequence();
    void chooseSide();

    // Continuous safety monitoring while an avoidance maneuver is in
    // progress (Section 14). Returns true if it took over (stopped
    // motors / changed state) and the caller's normal per-state timed
    // logic for this tick should be skipped.
    bool safetyInterruptCheck();

    void driveNormalMovementCheck();
    void driveObstacleDetected();
    void driveCheckingLeft();
    void driveCheckingRight();
    void driveChoosingPath();
    void driveAvoiding(bool isLeft);
    void drivePassingObstacle();
    void driveReacquiring();
    void driveResuming();
    void driveBlocked();
};

extern ObstacleAvoidance Obstacle;
