// =====================================================================
// AUTONEX_ESP32.ino
//
// AUTONEX low-level motor + obstacle-avoidance controller (ESP32).
//
// The Raspberry Pi is the ROUTE planner (QR navigation, face auth,
// lock, voice). This ESP32 is the reliable low-level executor:
// motors, ultrasonic safety, temporary local obstacle avoidance,
// watchdog. Obstacle avoidance NEVER changes the route the Pi commanded.
//
// loop() is fully non-blocking apart from short, bounded sensor
// sampling delays; every timed behavior is a millis() state machine.
//
// ---- Pi -> ESP32 (newline terminated, UART2) --------------------------
//   FORWARD BACKWARD STOP LEFT RIGHT TURN_LEFT_90 TURN_RIGHT_90
//   OBSTACLE_AVOID (alias of FORWARD; avoidance is always armed)
//   EMERGENCY_STOP  RESUME (clears a latched emergency/watchdog trip)
//   STATUS          (also acts as a heartbeat - send at least every
//                    ~1 s while moving or the watchdog stops the robot)
//
// ---- USB serial test mode (115200) ------------------------------------
//   F B L R S TL TR STATUS SENSORS AUTO ML MR ESTOP RESUME WDOG CAL HELP
// =====================================================================
#include "config.h"
#include "AutonexTypes.h"
#include "Calibration.h"
#include "Communication.h"
#include "MotorController.h"
#include "UltrasonicManager.h"
#include "ObstacleAvoidance.h"
#include "NavigationController.h"
#include "SafetyController.h"

// In USB test mode there is no Pi heartbeat, so the watchdog is
// suspended by default. Type WDOG to enforce it (needed for Test 15).
static bool usbControl = false;
static bool watchdogEnforcedInTest = false;

static void printHelp() {
    Comm.println(F("---- AUTONEX TEST MODE ----"));
    Comm.println(F("F/B forward/backward   L/R spin left/right   S stop"));
    Comm.println(F("TL/TR calibrated 90-degree turns"));
    Comm.println(F("ML/MR left/right motor alone forward (Test 1/2)"));
    Comm.println(F("SENSORS  print filtered F/L/R distances"));
    Comm.println(F("AUTO     forward with obstacle avoidance armed"));
    Comm.println(F("STATUS   ESTOP   RESUME   WDOG (toggle watchdog in test)"));
    Comm.println(F("CAL      enter calibration mode (SET/SHOW/SAVE/RESET/EXIT)"));
}

static void printSensors() {
    long f = Ultrasonic.getFrontDistance();
    long l = Ultrasonic.getLeftDistance();
    long r = Ultrasonic.getRightDistance();
    Comm.println(String("[ULTRASONIC] F=") + (f > 0 ? String(f) + "cm" : String("ERR")) +
                 " L=" + (l > 0 ? String(l) + "cm" : String("ERR")) +
                 " R=" + (r > 0 ? String(r) + "cm" : String("ERR")));
}

// Maps a validated Pi command word to a NavCommand. Returns false if
// the word is unknown (unknown input never moves the robot).
static bool parsePiCommand(const String &c, NavCommand &out) {
    if (c == "FORWARD" || c == "OBSTACLE_AVOID") { out = NavCommand::FORWARD; return true; }
    if (c == "BACKWARD")       { out = NavCommand::BACKWARD;       return true; }
    if (c == "STOP")           { out = NavCommand::STOP;           return true; }
    if (c == "LEFT")           { out = NavCommand::LEFT;           return true; }
    if (c == "RIGHT")          { out = NavCommand::RIGHT;          return true; }
    if (c == "TURN_LEFT_90")   { out = NavCommand::TURN_LEFT_90;   return true; }
    if (c == "TURN_RIGHT_90")  { out = NavCommand::TURN_RIGHT_90;  return true; }
    if (c == "EMERGENCY_STOP") { out = NavCommand::EMERGENCY_STOP; return true; }
    if (c == "RESUME")         { out = NavCommand::RESUME;         return true; }
    if (c == "STATUS")         { out = NavCommand::STATUS;         return true; }
    return false;
}

static void handlePiLine(const String &line) {
    usbControl = false;
    NavCommand cmd;
    if (parsePiCommand(line, cmd)) {
        Navigation.handleCommand(cmd);
    } else {
        Comm.log(F("COMM"), "UNKNOWN PI COMMAND: " + line);
        Comm.sendStatus(F("ERROR_UNKNOWN_COMMAND"));
    }
}

static void handleTestLine(const String &line) {

    // Calibration mode swallows its own commands first.
    if (Cal.isActive() && Cal.handleCommand(line)) return;

    usbControl = true;
    const int16_t spd = Cal.data().forwardSpeed;

    if (line == "HELP")         { printHelp(); }
    else if (line == "CAL")     { Cal.enter(); }
    else if (line == "SENSORS") { printSensors(); }
    else if (line == "WDOG")    {
        watchdogEnforcedInTest = !watchdogEnforcedInTest;
        Comm.println(String("[TEST] Watchdog in test mode: ") + (watchdogEnforcedInTest ? "ENFORCED" : "SUSPENDED"));
    }
    else if (line == "ML")      { Navigation.manualDrive(spd, 0);   Comm.println(F("[TEST] LEFT motor forward")); }
    else if (line == "MR")      { Navigation.manualDrive(0, spd);   Comm.println(F("[TEST] RIGHT motor forward")); }
    else if (line == "F" || line == "AUTO") { Navigation.handleCommand(NavCommand::FORWARD); }
    else if (line == "B")       { Navigation.handleCommand(NavCommand::BACKWARD); }
    else if (line == "L")       { Navigation.handleCommand(NavCommand::LEFT); }
    else if (line == "R")       { Navigation.handleCommand(NavCommand::RIGHT); }
    else if (line == "S")       { Navigation.handleCommand(NavCommand::STOP); }
    else if (line == "TL")      { Navigation.handleCommand(NavCommand::TURN_LEFT_90); }
    else if (line == "TR")      { Navigation.handleCommand(NavCommand::TURN_RIGHT_90); }
    else if (line == "STATUS")  { Navigation.handleCommand(NavCommand::STATUS); }
    else if (line == "ESTOP")   { Navigation.handleCommand(NavCommand::EMERGENCY_STOP); }
    else if (line == "RESUME")  { Navigation.handleCommand(NavCommand::RESUME); }
    else {
        // Allow full Pi vocabulary from USB too (e.g. TURN_LEFT_90).
        NavCommand cmd;
        if (parsePiCommand(line, cmd)) Navigation.handleCommand(cmd);
        else Comm.println("[TEST] Unknown command: " + line + "  (type HELP)");
    }
}

void setup() {
    Comm.begin();          // opens USB + Pi UART first so boot logs are visible
    Cal.begin();           // saved calibration (flash) or config.h defaults
    Motors.begin();        // motors guaranteed stopped before anything else
    Ultrasonic.begin();
    Safety.begin();
    Obstacle.begin();
    Navigation.begin();

    Comm.sendStatus(F("READY"));
    Comm.println(F("[STATUS] READY - type HELP for test mode"));
}

void loop() {
    Comm.update();

    if (Comm.hasPiCommand())   handlePiLine(Comm.takePiCommand());
    if (Comm.hasTestCommand()) handleTestLine(Comm.takeTestCommand());

    // Bench testing without a Pi: keep the watchdog fed unless the
    // tester asked to enforce it.
    if (usbControl && !watchdogEnforcedInTest) Safety.feedWatchdog();

    Safety.update(Navigation.isMotionCommanded());
    Navigation.update();
}
