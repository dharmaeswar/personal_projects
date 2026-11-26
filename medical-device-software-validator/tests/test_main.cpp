// Unit tests for the medical-device software validator.
// Dependency-free harness: each CHECK records a pass/fail; the binary exits
// non-zero unless every check passes.
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

#include "../src/alarms.h"
#include "../src/crc16.h"
#include "../src/defects.h"
#include "../src/parameters.h"
#include "../src/telemetry.h"

namespace {

using namespace meddev;

int g_passed = 0;
int g_failed = 0;

void check(bool condition, const std::string& name) {
    if (condition) {
        ++g_passed;
    } else {
        ++g_failed;
        std::cout << "FAIL: " << name << "\n";
    }
}

void test_crc16() {
    // Known CRC-16/CCITT-FALSE vector: "123456789" -> 0x29B1.
    const std::string input = "123456789";
    check(crc16_ccitt(reinterpret_cast<const std::uint8_t*>(input.data()),
                      input.size()) == 0x29B1,
          "crc16 known vector 123456789 == 0x29B1");
    check(crc16_ccitt(nullptr, 0) == 0xFFFF, "crc16 empty input == 0xFFFF");
    const std::uint8_t one[1] = {0x00};
    check(crc16_ccitt(one, 1) == 0xE1F0, "crc16 single zero byte == 0xE1F0");
}

void test_telemetry_round_trip() {
    Frame frame{7, 42, {12000, -300, 36}};
    std::vector<std::uint8_t> wire = encode_frame(frame);
    DecodeResult decoded = decode_frame(wire.data(), wire.size(), 42);
    check(decoded.ok(), "telemetry round trip decodes ok");
    check(decoded.frame.device_id == 7, "telemetry device id preserved");
    check(decoded.frame.sequence == 42, "telemetry sequence preserved");
    check(decoded.frame.readings.size() == 3 &&
              decoded.frame.readings[0] == 12000 &&
              decoded.frame.readings[1] == -300 &&
              decoded.frame.readings[2] == 36,
          "telemetry readings preserved incl. negative value");

    // Empty-reading frame.
    Frame empty{3, 1, {}};
    std::vector<std::uint8_t> empty_wire = encode_frame(empty);
    DecodeResult empty_decoded =
        decode_frame(empty_wire.data(), empty_wire.size(), 0);
    check(empty_decoded.ok() && empty_decoded.frame.readings.empty(),
          "telemetry empty frame round trip");
}

void test_telemetry_rejection() {
    Frame frame{7, 5, {100, 200}};
    std::vector<std::uint8_t> wire = encode_frame(frame);

    std::vector<std::uint8_t> corrupted = wire;
    corrupted[4] ^= 0xFF;  // flip a payload byte: CRC must catch it
    DecodeResult bad_crc =
        decode_frame(corrupted.data(), corrupted.size(), 5);
    check(!bad_crc.ok() && bad_crc.error == DecodeError::kBadCrc,
          "telemetry corrupted payload rejected as bad CRC");

    DecodeResult wrong_seq = decode_frame(wire.data(), wire.size(), 6);
    check(!wrong_seq.ok() && wrong_seq.error == DecodeError::kOutOfOrder,
          "telemetry out-of-order sequence rejected");

    DecodeResult short_frame = decode_frame(wire.data(), 3, 0);
    check(!short_frame.ok() && short_frame.error == DecodeError::kTooShort,
          "telemetry truncated frame rejected as too short");

    std::vector<std::uint8_t> truncated = wire;
    truncated.pop_back();  // drop a CRC byte: length no longer matches count
    DecodeResult bad_len =
        decode_frame(truncated.data(), truncated.size(), 0);
    check(!bad_len.ok() &&
              (bad_len.error == DecodeError::kBadCrc ||
               bad_len.error == DecodeError::kBadLength),
          "telemetry frame with dropped byte rejected");
}

void test_parameters() {
    ParameterSpec spec{"tip_temperature", "C", 20, 42, 15, 45};
    check(spec.valid(), "parameter spec bands are consistent");
    check(spec.check(36) == ReadingStatus::kOk, "parameter in-band is OK");
    check(spec.check(20) == ReadingStatus::kOk, "parameter safe-min edge is OK");
    check(spec.check(42) == ReadingStatus::kOk, "parameter safe-max edge is OK");
    check(spec.check(44) == ReadingStatus::kWarning,
          "parameter in warning band is WARNING");
    check(spec.check(15) == ReadingStatus::kWarning,
          "parameter warn-min edge is WARNING");
    check(spec.check(50) == ReadingStatus::kFail,
          "parameter outside warning band is FAIL");
    check(spec.check(10) == ReadingStatus::kFail,
          "parameter below warning band is FAIL");

    ParameterSpec bad{"broken", "x", 10, 5, 0, 20};  // safe_min > safe_max
    check(!bad.valid(), "parameter spec with inverted safe band is invalid");
}

void test_alarms() {
    AlarmEvaluator alarm(
        AlarmRule{"tip_temperature_high", 42.0, 2.0, Severity::kCritical});
    check(!alarm.update(38.0), "alarm quiet below threshold");
    check(!alarm.update(41.9), "alarm quiet just below threshold");
    check(alarm.update(42.0), "alarm trips at threshold");
    check(alarm.update(41.0), "alarm stays latched inside hysteresis band");
    check(!alarm.update(40.0), "alarm clears at threshold minus hysteresis");
    check(!alarm.active(), "alarm inactive after clearing");
    check(alarm.update(45.0), "alarm re-trips after clearing");
    alarm.acknowledge();
    check(!alarm.active(), "acknowledge clears a latched alarm");
}

void test_defects() {
    DefectTracker tracker;
    const int first = tracker.add("CRC failure on frame seq 4", Severity::kWarning);
    const int second =
        tracker.add("Tip temperature outside warning band", Severity::kCritical);
    check(first == 1 && second == 2, "defect ids assigned in order");
    check(tracker.open_count() == 2, "defect tracker counts two open defects");
    check(tracker.open_count(Severity::kCritical) == 1,
          "defect tracker counts one open critical defect");
    check(tracker.open_count(Severity::kInfo) == 0,
          "defect tracker counts zero open info defects");
    check(tracker.resolve(first), "defect resolve succeeds for open defect");
    check(!tracker.resolve(first), "defect resolve fails twice for same id");
    check(!tracker.resolve(999), "defect resolve fails for unknown id");
    check(tracker.open_count() == 1, "defect tracker counts one open defect left");
}

}  // namespace

int main() {
    test_crc16();
    test_telemetry_round_trip();
    test_telemetry_rejection();
    test_parameters();
    test_alarms();
    test_defects();
    std::cout << g_passed << " passed, " << g_failed << " failed\n";
    return g_failed == 0 ? 0 : 1;
}
