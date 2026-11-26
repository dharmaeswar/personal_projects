// Parameter range validation for surgical device readings.
//
// Each parameter (drill speed, irrigation flow, tip temperature, battery and
// similar) carries a safe operating band plus a wider warning band. A reading
// inside the safe band is OK, inside the warning band is a warning, and
// outside both is a failure that must raise a defect, never silently pass.
#pragma once
#include <string>

namespace meddev {

enum class ReadingStatus { kOk, kWarning, kFail };

struct ParameterSpec {
    std::string name;
    std::string unit;
    double safe_min = 0.0;
    double safe_max = 0.0;
    double warn_min = 0.0;  // warning band; must contain [safe_min, safe_max]
    double warn_max = 0.0;

    bool valid() const {
        return warn_min <= safe_min && safe_min <= safe_max &&
               safe_max <= warn_max;
    }
    ReadingStatus check(double value) const;
};

struct ParameterCheck {
    std::string name;
    double value = 0.0;
    ReadingStatus status = ReadingStatus::kOk;
    std::string message() const;
};

ParameterCheck validate_reading(const ParameterSpec& spec, double value);

}  // namespace meddev
