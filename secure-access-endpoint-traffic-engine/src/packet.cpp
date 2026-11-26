#include "traffic_engine.h"

#include <sstream>
#include <utility>

namespace gsa {

namespace {

// Parse one dotted-quad octet with strict bounds: 1-3 digits, 0-255,
// no leading '+'/'-' and no empty segments. Returns false on any bad input.
bool ParseOctet(const std::string& text, std::size_t begin, std::size_t end,
                std::uint32_t* out) {
    if (end <= begin || end - begin > 3) return false;
    std::uint32_t value = 0;
    for (std::size_t i = begin; i < end; ++i) {
        const char c = text[i];
        if (c < '0' || c > '9') return false;
        value = value * 10 + static_cast<std::uint32_t>(c - '0');
    }
    if (value > 255) return false;
    *out = value;
    return true;
}

bool EndsWith(const std::string& text, const std::string& suffix) {
    if (suffix.size() > text.size()) return false;
    return text.compare(text.size() - suffix.size(), suffix.size(), suffix) == 0;
}

}  // namespace

bool ParseIpv4(const std::string& text, std::uint32_t* out) {
    if (text.empty() || text.size() > 15) return false;
    std::uint32_t octets[4] = {0, 0, 0, 0};
    std::size_t start = 0;
    for (int i = 0; i < 4; ++i) {
        const std::size_t dot = text.find('.', start);
        const std::size_t end = (i == 3) ? text.size() : dot;
        if (i < 3 && dot == std::string::npos) return false;
        if (i == 3 && dot != std::string::npos) return false;
        if (!ParseOctet(text, start, end, &octets[i])) return false;
        start = dot + 1;
    }
    *out = (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3];
    return true;
}

bool CidrContains(const std::string& cidr, const std::string& ip) {
    const std::size_t slash = cidr.find('/');
    if (slash == std::string::npos) return false;
    std::uint32_t network = 0;
    std::uint32_t address = 0;
    if (!ParseIpv4(cidr.substr(0, slash), &network)) return false;
    if (!ParseIpv4(ip, &address)) return false;
    const std::string prefix_text = cidr.substr(slash + 1);
    if (prefix_text.empty() || prefix_text.size() > 2) return false;
    int prefix = 0;
    for (const char c : prefix_text) {
        if (c < '0' || c > '9') return false;
        prefix = prefix * 10 + (c - '0');
    }
    if (prefix < 0 || prefix > 32) return false;
    const std::uint32_t mask =
        prefix == 0 ? 0u : (0xFFFFFFFFu << (32 - prefix));
    return (network & mask) == (address & mask);
}

bool ValidatePacket(const Packet& packet, std::string* reason) {
    std::uint32_t ignored = 0;
    if (!ParseIpv4(packet.src_ip, &ignored)) {
        *reason = "malformed source address";
        return false;
    }
    if (!ParseIpv4(packet.dst_ip, &ignored)) {
        *reason = "malformed destination address";
        return false;
    }
    if (packet.protocol == Protocol::kUnknown) {
        *reason = "unknown protocol";
        return false;
    }
    if (packet.payload_bytes > Engine::kMaxPayloadBytes) {
        *reason = "payload exceeds 1 MiB bound";
        return false;
    }
    return true;
}

void Policy::AddRule(Rule rule) { rules_.push_back(std::move(rule)); }

Decision Policy::Evaluate(const Packet& packet) const {
    for (const Rule& rule : rules_) {
        if (rule.src_cidr && !CidrContains(*rule.src_cidr, packet.src_ip)) continue;
        if (rule.dst_cidr && !CidrContains(*rule.dst_cidr, packet.dst_ip)) continue;
        if (rule.protocol && *rule.protocol != packet.protocol) continue;
        if (rule.dst_port && *rule.dst_port != packet.dst_port) continue;
        if (rule.dns_suffix &&
            (packet.dns_name.empty() || !EndsWith(packet.dns_name, *rule.dns_suffix)))
            continue;
        if (rule.tls_sni &&
            (packet.tls_sni.empty() || packet.tls_sni != *rule.tls_sni))
            continue;
        Decision decision;
        decision.kind = rule.action == Action::kAllow ? DecisionKind::kAllowed
                                                      : DecisionKind::kBlocked;
        decision.rule_name = rule.name;
        decision.reason = rule.action == Action::kAllow
                              ? "matched allow rule " + rule.name
                              : "matched block rule " + rule.name;
        return decision;
    }
    Decision denied;
    denied.kind = DecisionKind::kBlocked;
    denied.rule_name = "default-deny";
    denied.reason = "no rule matched; default-deny";
    return denied;
}

std::string FiveTuple(const Packet& packet) {
    std::ostringstream out;
    out << packet.src_ip << ':' << packet.src_port << " -> " << packet.dst_ip
        << ':' << packet.dst_port << ' ' << ProtocolName(packet.protocol);
    return out.str();
}

std::string ProtocolName(Protocol protocol) {
    switch (protocol) {
        case Protocol::kTcp: return "TCP";
        case Protocol::kUdp: return "UDP";
        default: return "UNKNOWN";
    }
}

}  // namespace gsa
