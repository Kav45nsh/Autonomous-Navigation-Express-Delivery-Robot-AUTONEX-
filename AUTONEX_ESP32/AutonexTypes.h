// =====================================================================
// AutonexTypes.h
//
// Shared enums used by every module. Kept in one header so
// MotorController / NavigationController / ObstacleAvoidance /
// Communication can all refer to the same vocabulary without
// including each other (avoids circular #include problems).
// =====================================================================
#pragma once

// -------------------------------------------------------------------
// High level command coming from the Raspberry Pi (see Section 20/24
// of the design brief). The ESP32 never interprets QR codes itself -
// the Pi already translated a QR event into one of these.
// -------------------------------------------------------------------
enum class NavCommand {
    NONE,
    FORWARD,
    BACKWARD,
    STOP,
    LEFT,          // continuous left spin until STOP
    RIGHT,         // continuous right spin until STOP
    TURN_LEFT_90,
    TURN_RIGHT_90,
    MANUAL,        // bench-test raw motor drive (test mode only)
    EMERGENCY_STOP,
    RESUME,     // clears a latched emergency stop / watchdog trip (Section 32)
    STATUS
};

// -------------------------------------------------------------------
// Logical heading / "original_navigation_command" memory.
// This is what obstacle avoidance must NEVER permanently overwrite.
// -------------------------------------------------------------------
enum class Heading {
    FORWARD,
    BACKWARD,
    LEFT,
    RIGHT,
    STOPPED
};

// -------------------------------------------------------------------
// Obstacle-avoidance state machine (Section 9).
// -------------------------------------------------------------------
enum class ObstacleState {
    NORMAL_MOVEMENT,
    OBSTACLE_DETECTED,
    EMERGENCY_STOP,
    CHECKING_LEFT,
    CHECKING_RIGHT,
    CHOOSING_PATH,
    AVOIDING_LEFT,
    AVOIDING_RIGHT,
    PASSING_OBSTACLE,
    REACQUIRING_DIRECTION,
    RESUMING_MOVEMENT,
    BLOCKED
};

// -------------------------------------------------------------------
// Which side an avoidance maneuver picked / is currently using.
// -------------------------------------------------------------------
enum class AvoidSide {
    NONE,
    LEFT,
    RIGHT
};

// ---------------------------------------------------------------
// Human readable names, used everywhere we log or send status.
// ---------------------------------------------------------------
inline const char *navCommandToString(NavCommand c) {
    switch (c) {
        case NavCommand::NONE:           return "NONE";
        case NavCommand::FORWARD:        return "FORWARD";
        case NavCommand::BACKWARD:       return "BACKWARD";
        case NavCommand::STOP:           return "STOP";
        case NavCommand::LEFT:           return "LEFT";
        case NavCommand::RIGHT:          return "RIGHT";
        case NavCommand::MANUAL:         return "MANUAL";
        case NavCommand::TURN_LEFT_90:   return "TURN_LEFT_90";
        case NavCommand::TURN_RIGHT_90:  return "TURN_RIGHT_90";
        case NavCommand::EMERGENCY_STOP: return "EMERGENCY_STOP";
        case NavCommand::RESUME:         return "RESUME";
        case NavCommand::STATUS:         return "STATUS";
    }
    return "UNKNOWN";
}

inline const char *headingToString(Heading h) {
    switch (h) {
        case Heading::FORWARD:  return "FORWARD";
        case Heading::BACKWARD: return "BACKWARD";
        case Heading::LEFT:     return "LEFT";
        case Heading::RIGHT:    return "RIGHT";
        case Heading::STOPPED:  return "STOPPED";
    }
    return "UNKNOWN";
}

inline const char *obstacleStateToString(ObstacleState s) {
    switch (s) {
        case ObstacleState::NORMAL_MOVEMENT:      return "NORMAL_MOVEMENT";
        case ObstacleState::OBSTACLE_DETECTED:    return "OBSTACLE_DETECTED";
        case ObstacleState::EMERGENCY_STOP:       return "EMERGENCY_STOP";
        case ObstacleState::CHECKING_LEFT:        return "CHECKING_LEFT";
        case ObstacleState::CHECKING_RIGHT:       return "CHECKING_RIGHT";
        case ObstacleState::CHOOSING_PATH:        return "CHOOSING_PATH";
        case ObstacleState::AVOIDING_LEFT:        return "AVOIDING_LEFT";
        case ObstacleState::AVOIDING_RIGHT:       return "AVOIDING_RIGHT";
        case ObstacleState::PASSING_OBSTACLE:     return "PASSING_OBSTACLE";
        case ObstacleState::REACQUIRING_DIRECTION:return "REACQUIRING_DIRECTION";
        case ObstacleState::RESUMING_MOVEMENT:    return "RESUMING_MOVEMENT";
        case ObstacleState::BLOCKED:              return "BLOCKED";
    }
    return "UNKNOWN";
}
