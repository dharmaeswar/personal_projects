// Threshold alarms with hysteresis and latching.
#include "alarms.h"

namespace meddev {

bool AlarmEvaluator::update(double value) {
    if (!active_ && value >= rule_.threshold) {
        active_ = true;
    } else if (active_ && value <= rule_.threshold - rule_.hysteresis) {
        active_ = false;
    }
    return active_;
}

}  // namespace meddev
