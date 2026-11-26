// Demo: one scripted validation run over synthetic surgical-device telemetry.
//
// Six frames are encoded, one is corrupted in transit, and each decoded frame
// is checked against the parameter bands. Failures open defects; the run ends
// with a pass/fail summary and the open-defect count.
#include <cstdint>
#include <iostream>
#include <vector>

#include "alarms.h"
#include "defects.h"
#include "parameters.h"
#include "telemetry.h"

namespace {

using namespace meddev;

void print_check(const ParameterCheck& check) {
    std::cout << "  " << check.message() << "\n";
}

}  // namespace

int main() {
    const std::vector<ParameterSpec> specs = {
        {"drill_speed", "rpm", 8000, 30000, 5000, 35000},
        {"irrigation_flow", "ml/min", 10, 60, 5, 80},
        {"tip_temperature", "C", 20, 42, 15, 45},
    };
    AlarmEvaluator temp_alarm(
        AlarmRule{"tip_temperature_high", 42.0, 2.0, Severity::kCritical});
    DefectTracker defects;

    // Synthetic session: device 7, sequences 1..6. Frame 4 is corrupted.
    std::vector<Frame> session = {
        {7, 1, {12000, 30, 36}},
        {7, 2, {15000, 45, 38}},
        {7, 3, {28000, 55, 41}},
        {7, 4, {31000, 70, 44}},  // corrupted in transit below
        {7, 5, {9000, 20, 37}},
        {7, 6, {20000, 40, 39}},
    };

    int frames_ok = 0;
    int frames_rejected = 0;
    std::uint16_t expected = 1;
    for (const Frame& frame : session) {
        std::vector<std::uint8_t> wire = encode_frame(frame);
        if (frame.sequence == 4) {
            wire[5] ^= 0xFF;  // corrupt one payload byte in transit
        }
        DecodeResult decoded = decode_frame(wire.data(), wire.size(), expected);
        if (!decoded.ok()) {
            ++frames_rejected;
            defects.add("Rejected telemetry frame seq " +
                            std::to_string(frame.sequence),
                        Severity::kWarning);
            std::cout << "Frame seq " << frame.sequence << ": REJECTED\n";
            // Scripted session: the sender moves on, so the link resyncs to
            // the next sequence instead of rejecting every frame after the gap.
            expected = static_cast<std::uint16_t>(frame.sequence + 1);
            continue;
        }
        ++frames_ok;
        expected = static_cast<std::uint16_t>(frame.sequence + 1);
        std::cout << "Frame seq " << frame.sequence << ": decoded, "
                  << decoded.frame.readings.size() << " readings\n";
        for (std::size_t i = 0; i < specs.size() && i < decoded.frame.readings.size(); ++i) {
            ParameterCheck check = validate_reading(
                specs[i], static_cast<double>(decoded.frame.readings[i]));
            print_check(check);
            if (check.status == ReadingStatus::kFail) {
                defects.add(check.message(), Severity::kCritical);
            }
        }
        const double temp = static_cast<double>(decoded.frame.readings[2]);
        if (temp_alarm.update(temp)) {
            std::cout << "  ALARM ACTIVE: tip_temperature_high\n";
        }
    }

    std::cout << "Frames accepted: " << frames_ok
              << ", rejected: " << frames_rejected << "\n";
    std::cout << "Open defects: " << defects.open_count() << " (critical: "
              << defects.open_count(Severity::kCritical) << ")\n";
    std::cout << (defects.open_count() == 0 ? "VALIDATION PASSED\n"
                                            : "VALIDATION FAILED: open defects remain\n");
    return defects.open_count() == 0 ? 0 : 1;
}
