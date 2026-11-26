// Parameter range validation for surgical device readings.
#include "parameters.h"

namespace meddev {

ReadingStatus ParameterSpec::check(double value) const {
    if (value >= safe_min && value <= safe_max) return ReadingStatus::kOk;
    if (value >= warn_min && value <= warn_max) return ReadingStatus::kWarning;
    return ReadingStatus::kFail;
}

std::string ParameterCheck::message() const {
    switch (status) {
        case ReadingStatus::kOk:
            return name + " OK";
        case ReadingStatus::kWarning:
            return name + " WARNING: value " + std::to_string(value) +
                   " outside safe band";
        case ReadingStatus::kFail:
            return name + " FAIL: value " + std::to_string(value) +
                   " outside warning band";
    }
    return name + " UNKNOWN";
}

ParameterCheck validate_reading(const ParameterSpec& spec, double value) {
    ParameterCheck result;
    result.name = spec.name;
    result.value = value;
    result.status = spec.check(value);
    return result;
}

}  // namespace meddev
