// =====================================================================
// Communication.cpp
// =====================================================================
#include "Communication.h"
#include "config.h"

Communication Comm;

void Communication::begin() {
    Serial.begin(DEBUG_BAUD_RATE);

    PI_SERIAL.begin(PI_BAUD_RATE, SERIAL_8N1, PI_RX_PIN, PI_TX_PIN);

    _piBuffer.reserve(64);
    _testBuffer.reserve(64);

    Serial.println(F("[COMM] USB debug/test serial ready."));
    Serial.println(F("[COMM] Pi link (UART2) ready."));
}

// ---------------------------------------------------------------
// Non-blocking line reader shared by both ports.
// ---------------------------------------------------------------
void Communication::feedLine(Stream &port, String &buffer, String &outCommand, bool &readyFlag) {

    while (port.available() > 0) {

        char c = (char)port.read();

        if (c == '\r') {
            continue; // ignore CR, only \n terminates a line
        }

        if (c == '\n') {
            buffer.trim();
            if (buffer.length() > 0) {
                outCommand = buffer;
                outCommand.toUpperCase();
                readyFlag = true;
            }
            buffer = "";
            // Only surface one command per update() call so the main
            // loop always sees commands in order and nothing is lost
            // if two arrive back-to-back; remaining bytes stay
            // buffered in the port and are picked up next call.
            return;
        }

        if (buffer.length() < 63) {
            buffer += c;
        } else {
            // Runaway line (noise / bad wiring) - drop it defensively.
            buffer = "";
        }
    }
}

void Communication::update() {
    feedLine(PI_SERIAL, _piBuffer, _piCommand, _piReady);
    feedLine(Serial, _testBuffer, _testCommand, _testReady);
}

String Communication::takePiCommand() {
    _piReady = false;
    return _piCommand;
}

String Communication::takeTestCommand() {
    _testReady = false;
    return _testCommand;
}

void Communication::sendStatus(const String &status) {
    PI_SERIAL.print(status);
    PI_SERIAL.print('\n');

    Serial.print(F("[STATUS] "));
    Serial.println(status);
}

bool Communication::shouldLog(const String &tag) {
    unsigned long now = millis();

    for (int i = 0; i < _logTagCount; i++) {
        if (_logTags[i] == tag) {
            if (now - _logLastTime[i] >= LOG_INTERVAL_MS) {
                _logLastTime[i] = now;
                return true;
            }
            return false;
        }
    }

    // New tag we haven't seen before - log it immediately and start tracking.
    if (_logTagCount < MAX_LOG_TAGS) {
        _logTags[_logTagCount] = tag;
        _logLastTime[_logTagCount] = now;
        _logTagCount++;
    }
    return true;
}

void Communication::println(const String &line) {
    Serial.println(line);
}

void Communication::logThrottled(const String &tag, const String &message) {
    if (!shouldLog(tag)) {
        return;
    }
    log(tag, message);
}

void Communication::log(const String &tag, const String &message) {
    Serial.print('[');
    Serial.print(tag);
    Serial.print(F("] "));
    Serial.println(message);
}
