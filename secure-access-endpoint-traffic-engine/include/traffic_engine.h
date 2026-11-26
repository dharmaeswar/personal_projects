#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace gsa {

// ---------------------------------------------------------------------------
// Packet model: a synthetic endpoint packet. Addresses are dotted-quad
// IPv4 strings; dns_name / tls_sni are the names the endpoint observed
// for the flow (no real DNS resolution or TLS handshake happens here).
// ---------------------------------------------------------------------------
enum class Protocol { kTcp, kUdp, kUnknown };

enum class Action { kAllow, kBlock };

enum class DecisionKind { kAllowed, kBlocked, kQuarantined };

struct Packet {
    std::string src_ip;
    std::string dst_ip;
    std::uint16_t src_port = 0;
    std::uint16_t dst_port = 0;
    Protocol protocol = Protocol::kUnknown;
    std::string dns_name;   // empty when the flow carried no DNS name
    std::string tls_sni;    // empty when the flow carried no TLS SNI
    std::size_t payload_bytes = 0;
    std::uint64_t seq = 0;  // sender-assigned sequence, used for dedupe
};

struct Decision {
    DecisionKind kind = DecisionKind::kQuarantined;
    std::string rule_name;  // rule that fired, or "default-deny"/"malformed"
    std::string reason;     // one-line human-readable explanation
};

// ---------------------------------------------------------------------------
// Policy: ordered first-match rules, default-deny. An empty optional
// field means "any". CIDR is a dotted-quad prefix such as "10.0.0.0/8".
// ---------------------------------------------------------------------------
struct Rule {
    std::string name;
    Action action = Action::kBlock;
    std::optional<std::string> src_cidr;
    std::optional<std::string> dst_cidr;
    std::optional<Protocol> protocol;
    std::optional<std::uint16_t> dst_port;  // 0 is never a valid match
    std::optional<std::string> dns_suffix;  // packet dns_name must end here
    std::optional<std::string> tls_sni;     // exact SNI match
};

class Policy {
public:
    void AddRule(Rule rule);
    // First matching rule wins; no match is default-deny (block).
    Decision Evaluate(const Packet& packet) const;
    std::size_t RuleCount() const { return rules_.size(); }

private:
    std::vector<Rule> rules_;
};

// Bounds-checked IPv4 helpers. Returns false on any malformed input.
bool ParseIpv4(const std::string& text, std::uint32_t* out);
bool CidrContains(const std::string& cidr, const std::string& ip);

// Validate a packet before it reaches the policy engine.
bool ValidatePacket(const Packet& packet, std::string* reason);

// ---------------------------------------------------------------------------
// Diagnostics: append-only trace log + per-packet capture records.
// ---------------------------------------------------------------------------
struct CaptureRecord {
    std::uint64_t seq = 0;
    std::string five_tuple;
    Decision decision;
};

struct Snapshot {
    std::uint64_t processed = 0;
    std::uint64_t allowed = 0;
    std::uint64_t blocked = 0;
    std::uint64_t quarantined = 0;
    std::uint64_t evicted = 0;
    std::size_t connections = 0;
    std::vector<std::string> recent_traces;
};

class Diagnostics {
public:
    void Trace(const std::string& line);
    void Capture(const CaptureRecord& record);
    std::vector<std::string> RecentTraces(std::size_t n) const;
    std::size_t CaptureCount() const;

private:
    mutable std::mutex mutex_;
    std::deque<std::string> traces_;
    std::vector<CaptureRecord> captures_;
};

// ---------------------------------------------------------------------------
// Engine: policy + bounded connection table + worker pool.
// ---------------------------------------------------------------------------
struct ConnectionState {
    std::uint64_t packets = 0;
    std::uint64_t bytes = 0;
    std::uint64_t last_seq = 0;
};

class Engine {
public:
    static constexpr std::size_t kMaxConnections = 1024;
    static constexpr std::size_t kMaxPayloadBytes = 1024 * 1024;  // 1 MiB

    explicit Engine(Policy policy);

    // Classify one packet: validate, evaluate policy, update state.
    Decision Process(const Packet& packet);

    // Process packets concurrently with `threads` workers.
    void RunConcurrent(const std::vector<Packet>& packets, std::size_t threads);

    Snapshot TakeSnapshot(std::size_t recent_traces = 10) const;
    std::size_t ConnectionCount() const;

    // Canary (shadow) evaluation: evaluate `candidate` next to the active
    // policy and count divergences. The candidate never enforces anything.
    std::uint64_t CanaryDivergences(const Policy& candidate,
                                    const std::vector<Packet>& packets) const;

private:
    std::string ConnectionKey(const Packet& packet) const;
    void TouchConnection(const Packet& packet);

    Policy policy_;
    Diagnostics diagnostics_;
    mutable std::mutex state_mutex_;
    std::unordered_map<std::string, ConnectionState> connections_;
    std::deque<std::string> connection_order_;  // insertion order, for eviction
    std::atomic<std::uint64_t> processed_{0};
    std::atomic<std::uint64_t> allowed_{0};
    std::atomic<std::uint64_t> blocked_{0};
    std::atomic<std::uint64_t> quarantined_{0};
    std::atomic<std::uint64_t> evicted_{0};
};

std::string FiveTuple(const Packet& packet);
std::string ProtocolName(Protocol protocol);

}  // namespace gsa
