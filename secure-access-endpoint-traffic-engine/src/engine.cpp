#include "traffic_engine.h"

#include <condition_variable>
#include <queue>
#include <thread>
#include <utility>

namespace gsa {

Engine::Engine(Policy policy) : policy_(std::move(policy)) {}

std::string Engine::ConnectionKey(const Packet& packet) const {
    return FiveTuple(packet);
}

void Engine::TouchConnection(const Packet& packet) {
    std::lock_guard<std::mutex> lock(state_mutex_);
    const std::string key = ConnectionKey(packet);
    auto it = connections_.find(key);
    if (it == connections_.end()) {
        // Bounded table: evict the oldest connection before growing past
        // the cap, so memory stays flat under a flood of new flows.
        if (connections_.size() >= kMaxConnections) {
            const std::string oldest = connection_order_.front();
            connection_order_.pop_front();
            connections_.erase(oldest);
            evicted_.fetch_add(1, std::memory_order_relaxed);
        }
        ConnectionState state;
        state.packets = 1;
        state.bytes = packet.payload_bytes;
        state.last_seq = packet.seq;
        connections_.emplace(key, state);
        connection_order_.push_back(key);
    } else {
        it->second.packets += 1;
        it->second.bytes += packet.payload_bytes;
        it->second.last_seq = packet.seq;
    }
}

Decision Engine::Process(const Packet& packet) {
    processed_.fetch_add(1, std::memory_order_relaxed);
    std::string problem;
    if (!ValidatePacket(packet, &problem)) {
        quarantined_.fetch_add(1, std::memory_order_relaxed);
        Decision decision;
        decision.kind = DecisionKind::kQuarantined;
        decision.rule_name = "malformed";
        decision.reason = problem;
        diagnostics_.Trace("QUARANTINE seq=" + std::to_string(packet.seq) + " " + problem);
        diagnostics_.Capture(CaptureRecord{packet.seq, FiveTuple(packet), decision});
        return decision;
    }
    Decision decision = policy_.Evaluate(packet);
    if (decision.kind == DecisionKind::kAllowed) {
        allowed_.fetch_add(1, std::memory_order_relaxed);
        TouchConnection(packet);
    } else {
        blocked_.fetch_add(1, std::memory_order_relaxed);
    }
    diagnostics_.Trace((decision.kind == DecisionKind::kAllowed ? "ALLOW " : "BLOCK ") +
                       std::to_string(packet.seq) + " " + FiveTuple(packet) + " [" +
                       decision.rule_name + "]");
    diagnostics_.Capture(CaptureRecord{packet.seq, FiveTuple(packet), decision});
    return decision;
}

void Engine::RunConcurrent(const std::vector<Packet>& packets, std::size_t threads) {
    if (threads == 0) threads = 1;
    std::queue<const Packet*> work;
    for (const Packet& packet : packets) work.push(&packet);
    std::mutex queue_mutex;
    std::condition_variable queue_cv;
    bool done = false;
    auto worker = [&]() {
        for (;;) {
            const Packet* packet = nullptr;
            {
                std::unique_lock<std::mutex> lock(queue_mutex);
                queue_cv.wait(lock, [&] { return done || !work.empty(); });
                if (work.empty()) {
                    if (done) return;
                    continue;
                }
                packet = work.front();
                work.pop();
            }
            Process(*packet);
        }
    };
    std::vector<std::thread> pool;
    for (std::size_t i = 0; i < threads; ++i) pool.emplace_back(worker);
    {
        std::lock_guard<std::mutex> lock(queue_mutex);
        done = true;
    }
    queue_cv.notify_all();
    for (std::thread& thread : pool) thread.join();
}

Snapshot Engine::TakeSnapshot(std::size_t recent_traces) const {
    Snapshot snapshot;
    snapshot.processed = processed_.load(std::memory_order_relaxed);
    snapshot.allowed = allowed_.load(std::memory_order_relaxed);
    snapshot.blocked = blocked_.load(std::memory_order_relaxed);
    snapshot.quarantined = quarantined_.load(std::memory_order_relaxed);
    snapshot.evicted = evicted_.load(std::memory_order_relaxed);
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        snapshot.connections = connections_.size();
    }
    snapshot.recent_traces = diagnostics_.RecentTraces(recent_traces);
    return snapshot;
}

std::size_t Engine::ConnectionCount() const {
    std::lock_guard<std::mutex> lock(state_mutex_);
    return connections_.size();
}

std::uint64_t Engine::CanaryDivergences(const Policy& candidate,
                                        const std::vector<Packet>& packets) const {
    std::uint64_t divergences = 0;
    for (const Packet& packet : packets) {
        std::string problem;
        if (!ValidatePacket(packet, &problem)) continue;  // malformed: no policy call
        const Decision active = policy_.Evaluate(packet);
        const Decision shadow = candidate.Evaluate(packet);
        if (active.kind != shadow.kind) ++divergences;
    }
    return divergences;
}

}  // namespace gsa
