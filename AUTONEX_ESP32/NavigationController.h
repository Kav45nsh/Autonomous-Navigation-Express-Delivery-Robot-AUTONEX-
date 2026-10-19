// =====================================================================
// NavigationController.h
//
// The top-level orchestrator. Owns:
//   - current_command / previous_command / original_navigation_command
//     (Section 22 "command memory")
//   - the calibrated, non-blocking 90-degree turn controller (Section 17/18)
//   - command priority (Section 21): emergency > obstacle safety > STOP >
//     turn > movement > status
//
// It deliberately does NOT own obstacle-avoidance logic itself - that
// lives entirely in ObstacleAvoidance, which this class only calls into
// while the commanded heading is FORWARD. This split is what makes
// "obstacle avoidance is temporary, the route is permanent" (Section 12)
// structurally true rather than something that has to be remembered.
// =====================================================================
#pragma once

#include <Arduino.h>
#include "AutonexTypes.h"

class NavigationController {
public:
    void begin();

    // Called once per newly-received, validated command (from the Pi
    // link or from test mode). Updates command memory and kicks off
    // the appropriate motor behavior.
    void handleCommand(NavCommand cmd);

    // Must be called every loop() iteration regardless of whether a new
    // command arrived - this is what actually drives the motors frame
    // by frame (turns, forward + obstacle avoidance, etc.).
    void update();

    NavCommand currentCommand() const { return _currentCommand; }
    NavCommand previousCommand() const { return _previousCommand; }
    NavCommand originalNavigationCommand() const { return _originalNavigationCommand; }

    void sendFullStatus();

    // Bench-test only: drive raw signed PWM on each side (test mode ML/MR).
    void manualDrive(int16_t left, int16_t right);

    // True while any motion command is active (drives the comms watchdog).
    bool isMotionCommanded() const;

private:
    NavCommand _currentCommand = NavCommand::NONE;
    NavCommand _previousCommand = NavCommand::NONE;
    NavCommand _originalNavigationCommand = NavCommand::NONE;
    NavCommand _lastSafeDirection = NavCommand::NONE;
    unsigned long _lastCommandTime = 0;
    int16_t _manualLeft = 0;
    int16_t _manualRight = 0;

    // ---- 90-degree turn sub-state machine ----
    enum class TurnPhase {
        NONE,
        SPINNING,
        DECELERATING,
        SETTLING
    };

    TurnPhase _turnPhase = TurnPhase::NONE;
    bool _turnIsLeft = false;
    unsigned long _turnPhaseStart = 0;

    void updateTurn();
    void startTurn(bool isLeft);
};

extern NavigationController Navigation;
