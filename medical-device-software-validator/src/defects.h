// Defect tracking (the Jira-side record for this project).
//
// Every failed parameter check and every rejected telemetry frame opens a
// defect with a severity; defects are resolved explicitly and the tracker
// reports how many remain open per severity, so a validation run ends with
// a concrete open-defect count instead of a silent pass.
#pragma once
#include <string>
#include <vector>

#include "alarms.h"

namespace meddev {

enum class DefectStatus { kOpen, kResolved };

struct Defect {
    int id = 0;
    std::string title;
    Severity severity = Severity::kWarning;
    DefectStatus status = DefectStatus::kOpen;
};

class DefectTracker {
   public:
    int add(std::string title, Severity severity);
    bool resolve(int id);
    std::size_t open_count() const;
    std::size_t open_count(Severity severity) const;
    const std::vector<Defect>& defects() const { return defects_; }

   private:
    std::vector<Defect> defects_;
    int next_id_ = 1;
};

}  // namespace meddev
