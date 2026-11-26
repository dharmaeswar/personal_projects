// Defect tracking (the Jira-side record for this project).
#include "defects.h"

#include <algorithm>

namespace meddev {

int DefectTracker::add(std::string title, Severity severity) {
    Defect defect;
    defect.id = next_id_++;
    defect.title = std::move(title);
    defect.severity = severity;
    defects_.push_back(defect);
    return defect.id;
}

bool DefectTracker::resolve(int id) {
    for (Defect& defect : defects_) {
        if (defect.id == id && defect.status == DefectStatus::kOpen) {
            defect.status = DefectStatus::kResolved;
            return true;
        }
    }
    return false;
}

std::size_t DefectTracker::open_count() const {
    return static_cast<std::size_t>(std::count_if(
        defects_.begin(), defects_.end(), [](const Defect& d) {
            return d.status == DefectStatus::kOpen;
        }));
}

std::size_t DefectTracker::open_count(Severity severity) const {
    return static_cast<std::size_t>(std::count_if(
        defects_.begin(), defects_.end(), [severity](const Defect& d) {
            return d.status == DefectStatus::kOpen && d.severity == severity;
        }));
}

}  // namespace meddev
