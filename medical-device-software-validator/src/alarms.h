// Threshold alarms with hysteresis and latching.
//
// A high alarm trips when a reading reaches the threshold and stays latched
// until the reading falls back below (threshold - hysteresis). That stops a
// noisy signal hovering at the limit from flapping the alarm on and off, and
// the latched state is only cleared by an explicit acknowledge, as a device
// operator would do after investigating.
#pragma once
#include <string>

namespace meddev {

enum class Severity { kInfo, kWarning, kCritical };

struct AlarmRule {
    std::string name;
    double threshold = 0.0;
    double hysteresis = 0.0;  // must be >= 0 and < threshold span used
    Severity severity = Severity::kWarning;

    bool valid() const { return hysteresis >= 0.0; }
};

class AlarmEvaluator {
   public:
    explicit AlarmEvaluator(AlarmRule rule) : rule_(rule) {}

    // Feeds one reading; returns true while the alarm is active (latched).
    bool update(double value);
    bool active() const { return active_; }
    void acknowledge() { active_ = false; }
    const AlarmRule& rule() const { return rule_; }

   private:
    AlarmRule rule_;
    bool active_ = false;
};

}  // namespace meddev
