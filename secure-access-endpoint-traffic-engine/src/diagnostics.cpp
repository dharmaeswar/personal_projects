#include "traffic_engine.h"

namespace gsa {

void Diagnostics::Trace(const std::string& line) {
    std::lock_guard<std::mutex> lock(mutex_);
    traces_.push_back(line);
    if (traces_.size() > 1000) traces_.pop_front();  // bounded log, no growth
}

void Diagnostics::Capture(const CaptureRecord& record) {
    std::lock_guard<std::mutex> lock(mutex_);
    captures_.push_back(record);
}

std::vector<std::string> Diagnostics::RecentTraces(std::size_t n) const {
    std::lock_guard<std::mutex> lock(mutex_);
    std::vector<std::string> out;
    const std::size_t start = traces_.size() > n ? traces_.size() - n : 0;
    for (std::size_t i = start; i < traces_.size(); ++i) out.push_back(traces_[i]);
    return out;
}

std::size_t Diagnostics::CaptureCount() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return captures_.size();
}

}  // namespace gsa
