// =====================================================================
// Communication.h
//
// All Serial/Serial2 access lives here - nowhere else in the codebase
// should touch Serial or Serial2 directly. This keeps the protocol
// (newline-terminated ASCII commands, status strings) isolated from
// motor/navigation logic, per the design brief's Section 20.
//
// Two independent line-buffered channels:
//   - PI_SERIAL (UART2): high-level commands from the Raspberry Pi,
//     and status messages sent back to it.
//   - Serial (USB): debug logging, plus the standalone test/calibration
//     command set (Sections 28-29) so the robot can be exercised on the
//     bench without the Pi attached at all.
// =====================================================================
#pragma once

#include <Arduino.h>

class Communication {
public:
    void begin();

    // Must be called every loop() iteration - drains both serial
    // ports into line buffers without blocking.
    void update();

    bool hasPiCommand() const { return _piReady; }
    String takePiCommand();          // clears the ready flag

    bool hasTestCommand() const { return _testReady; }
    String takeTestCommand();        // clears the ready flag

    // Sends a status line to the Pi (e.g. "READY", "OBSTACLE_DETECTED")
    // AND mirrors it to the USB debug log.
    void sendStatus(const String &status);

    // Event log line (USB only), never dropped: "[TAG] message".
    void log(const String &tag, const String &message);

    // Same, but rate-limited per tag to LOG_INTERVAL_MS. Use for
    // periodic/repeating lines (sensor readings, "emergency active").
    void logThrottled(const String &tag, const String &message);

    // Raw unthrottled USB line (SENSORS dump, help text, etc.)
    void println(const String &line);

private:
    String _piBuffer;
    String _testBuffer;

    String _piCommand;
    String _testCommand;

    bool _piReady = false;
    bool _testReady = false;

    // Simple 2-slot rate limiter (enough tags for this project: MOTOR,
    // ULTRASONIC, OBSTACLE). Extend the arrays if more tags are needed.
    static const int MAX_LOG_TAGS = 6;
    String _logTags[MAX_LOG_TAGS];
    unsigned long _logLastTime[MAX_LOG_TAGS] = {0};
    int _logTagCount = 0;

    void feedLine(Stream &port, String &buffer, String &outCommand, bool &readyFlag);
    bool shouldLog(const String &tag);
};

extern Communication Comm;
