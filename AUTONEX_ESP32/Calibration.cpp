// =====================================================================
// Calibration.cpp
// =====================================================================
#include "Calibration.h"
#include "config.h"
#include "Communication.h"

Calibration Cal;

static const char *NVS_NAMESPACE = "autonex_cal";

void Calibration::resetToDefaults() {
    _data.leftInverted      = LEFT_MOTOR_INVERTED;
    _data.rightInverted     = RIGHT_MOTOR_INVERTED;
    _data.leftCorrection    = LEFT_MOTOR_CORRECTION;
    _data.rightCorrection   = RIGHT_MOTOR_CORRECTION;
    _data.forwardSpeed      = FORWARD_SPEED;
    _data.turnSpeed         = TURN_SPEED;
    _data.turnLeft90Ms      = TURN_LEFT_90_MS;
    _data.turnRight90Ms     = TURN_RIGHT_90_MS;
    _data.obstacleStopDistance = OBSTACLE_STOP_DISTANCE;
    _data.sideClearDistance    = SIDE_CLEAR_DISTANCE;
}

void Calibration::load() {
    if (!_prefs.begin(NVS_NAMESPACE, true /* read-only */)) {
        return; // namespace doesn't exist yet - keep defaults
    }

    _data.leftInverted   = _prefs.getBool("linv", _data.leftInverted);
    _data.rightInverted  = _prefs.getBool("rinv", _data.rightInverted);
    _data.leftCorrection = _prefs.getFloat("lcorr", _data.leftCorrection);
    _data.rightCorrection= _prefs.getFloat("rcorr", _data.rightCorrection);
    _data.forwardSpeed   = (uint8_t)_prefs.getUInt("fspeed", _data.forwardSpeed);
    _data.turnSpeed      = (uint8_t)_prefs.getUInt("tspeed", _data.turnSpeed);
    _data.turnLeft90Ms   = (uint16_t)_prefs.getUInt("lturn", _data.turnLeft90Ms);
    _data.turnRight90Ms  = (uint16_t)_prefs.getUInt("rturn", _data.turnRight90Ms);
    _data.obstacleStopDistance = _prefs.getInt("obstacle", _data.obstacleStopDistance);
    _data.sideClearDistance    = _prefs.getInt("side", _data.sideClearDistance);

    _prefs.end();
}

void Calibration::save() {
    if (!_prefs.begin(NVS_NAMESPACE, false /* read-write */)) {
        Comm.log(F("CAL"), F("FAILED TO OPEN NVS FOR WRITE"));
        return;
    }

    _prefs.putBool("linv", _data.leftInverted);
    _prefs.putBool("rinv", _data.rightInverted);
    _prefs.putFloat("lcorr", _data.leftCorrection);
    _prefs.putFloat("rcorr", _data.rightCorrection);
    _prefs.putUInt("fspeed", _data.forwardSpeed);
    _prefs.putUInt("tspeed", _data.turnSpeed);
    _prefs.putUInt("lturn", _data.turnLeft90Ms);
    _prefs.putUInt("rturn", _data.turnRight90Ms);
    _prefs.putInt("obstacle", _data.obstacleStopDistance);
    _prefs.putInt("side", _data.sideClearDistance);

    _prefs.end();

    Comm.log(F("CAL"), F("SAVED TO FLASH"));
}

void Calibration::begin() {
    resetToDefaults();
    load(); // overwrite with anything previously saved
}

void Calibration::enter() {
    _active = true;
    Comm.sendStatus(F("CALIBRATION_MODE"));
    printAll();
}

void Calibration::exit() {
    _active = false;
    Comm.sendStatus(F("CALIBRATION_EXIT"));
}

void Calibration::printAll() {
    Serial.println(F("---- AUTONEX CALIBRATION ----"));
    Serial.print(F("LINV    (left inverted)      = ")); Serial.println(_data.leftInverted);
    Serial.print(F("RINV    (right inverted)     = ")); Serial.println(_data.rightInverted);
    Serial.print(F("LCORR   (left correction)    = ")); Serial.println(_data.leftCorrection, 3);
    Serial.print(F("RCORR   (right correction)   = ")); Serial.println(_data.rightCorrection, 3);
    Serial.print(F("FSPEED  (forward speed)      = ")); Serial.println(_data.forwardSpeed);
    Serial.print(F("TSPEED  (turn speed)         = ")); Serial.println(_data.turnSpeed);
    Serial.print(F("LTURN   (left 90 turn ms)    = ")); Serial.println(_data.turnLeft90Ms);
    Serial.print(F("RTURN   (right 90 turn ms)   = ")); Serial.println(_data.turnRight90Ms);
    Serial.print(F("OBSTACLE(stop distance cm)   = ")); Serial.println(_data.obstacleStopDistance);
    Serial.print(F("SIDE    (side clear cm)      = ")); Serial.println(_data.sideClearDistance);
    Serial.println(F("------------------------------"));
    Serial.println(F("Commands: SET <NAME> <VALUE> | SHOW | SAVE | RESET | EXIT"));
}

bool Calibration::setByName(const String &name, const String &value) {

    if (name == "LINV")    { _data.leftInverted  = (value == "1" || value == "TRUE"); return true; }
    if (name == "RINV")    { _data.rightInverted = (value == "1" || value == "TRUE"); return true; }
    if (name == "LCORR")   { _data.leftCorrection  = value.toFloat(); return true; }
    if (name == "RCORR")   { _data.rightCorrection = value.toFloat(); return true; }
    if (name == "FSPEED")  { _data.forwardSpeed = (uint8_t)constrain(value.toInt(), 0, MAX_PWM); return true; }
    if (name == "TSPEED")  { _data.turnSpeed    = (uint8_t)constrain(value.toInt(), 0, MAX_PWM); return true; }
    if (name == "LTURN")   { _data.turnLeft90Ms  = (uint16_t)value.toInt(); return true; }
    if (name == "RTURN")   { _data.turnRight90Ms = (uint16_t)value.toInt(); return true; }
    if (name == "OBSTACLE"){ _data.obstacleStopDistance = value.toInt(); return true; }
    if (name == "SIDE")    { _data.sideClearDistance = value.toInt(); return true; }

    return false;
}

bool Calibration::handleCommand(const String &cmd) {

    if (cmd == "SHOW") { printAll(); return true; }
    if (cmd == "SAVE") { save(); return true; }
    if (cmd == "RESET") { resetToDefaults(); printAll(); return true; }
    if (cmd == "EXIT") { exit(); return true; }

    if (cmd.startsWith("SET ")) {
        String rest = cmd.substring(4);
        rest.trim();
        int sep = rest.indexOf(' ');
        if (sep < 0) {
            Serial.println(F("[CAL] Usage: SET <NAME> <VALUE>"));
            return true;
        }
        String name = rest.substring(0, sep);
        String value = rest.substring(sep + 1);
        value.trim();

        if (setByName(name, value)) {
            Serial.print(F("[CAL] ")); Serial.print(name); Serial.print(F(" = ")); Serial.println(value);
        } else {
            Serial.print(F("[CAL] Unknown parameter: ")); Serial.println(name);
        }
        return true;
    }

    return false;
}
