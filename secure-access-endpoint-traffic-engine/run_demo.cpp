// Demo: seed 240 synthetic endpoint packets, run them through a
// 4-worker engine, then compare a canary policy in shadow mode.
#include <iostream>
#include <string>
#include <vector>

#include "traffic_engine.h"

using namespace gsa;

static Packet MakePacket(std::uint64_t i) {
    Packet p;
    p.seq = i;
    p.src_ip = "10.1.2.3";
    p.src_port = static_cast<std::uint16_t>(40000 + (i % 20000));
    p.payload_bytes = 200 + (i % 1400);
    const int kind = static_cast<int>(i % 10);
    if (kind < 5) {  // corporate HTTPS
        p.dst_ip = "10.20.30.40";
        p.dst_port = 443;
        p.protocol = Protocol::kTcp;
        p.tls_sni = "login.corp.example";
    } else if (kind == 5) {  // corporate DNS
        p.dst_ip = "10.20.30.53";
        p.dst_port = 53;
        p.protocol = Protocol::kUdp;
        p.dns_name = "host.corp.example";
    } else if (kind == 6 || kind == 7) {  // unlisted external web
        p.dst_ip = "203.0.113.9";
        p.dst_port = 80;
        p.protocol = Protocol::kTcp;
    } else if (kind == 8) {  // blocked SNI
        p.dst_ip = "198.51.100.7";
        p.dst_port = 443;
        p.protocol = Protocol::kTcp;
        p.tls_sni = "evil.example.com";
    } else {  // planted malformed: every 10th packet in this slot
        p.dst_ip = "bad-address";
        p.dst_port = 443;
        p.protocol = Protocol::kTcp;
    }
    // 5 of the 240 are oversized instead of bad-address (i = 19, 59, ...).
    if (i % 40 == 19) {
        p.dst_ip = "10.20.30.40";
        p.payload_bytes = 2 * 1024 * 1024;
    }
    return p;
}

int main() {
    Policy policy;
    policy.AddRule(Rule{"allow-corp-https", Action::kAllow, "10.0.0.0/8",
                        "10.0.0.0/8", Protocol::kTcp, 443, std::nullopt,
                        std::nullopt});
    policy.AddRule(Rule{"allow-corp-dns", Action::kAllow, "10.0.0.0/8",
                        std::nullopt, Protocol::kUdp, 53, std::nullopt,
                        std::nullopt});
    policy.AddRule(Rule{"block-bad-sni", Action::kBlock, std::nullopt,
                        std::nullopt, Protocol::kTcp, 443, std::nullopt,
                        "evil.example.com"});
    policy.AddRule(Rule{"allow-trusted-sni", Action::kAllow, std::nullopt,
                        std::nullopt, Protocol::kTcp, 443, std::nullopt,
                        "login.corp.example"});

    std::vector<Packet> packets;
    for (std::uint64_t i = 0; i < 240; ++i) packets.push_back(MakePacket(i));

    Engine engine(policy);
    engine.RunConcurrent(packets, 4);
    const Snapshot snap = engine.TakeSnapshot(5);
    std::cout << "processed=" << snap.processed << " allowed=" << snap.allowed
              << " blocked=" << snap.blocked
              << " quarantined=" << snap.quarantined
              << " connections=" << snap.connections
              << " evicted=" << snap.evicted << "\n";

    // Canary: a candidate that blocks all TCP 443 first and carries no DNS
    // rule (stricter), in shadow mode — it would flip the 120
    // corporate-HTTPS allows and the 24 DNS allows to blocks (144 total).
    Policy canary;
    canary.AddRule(Rule{"canary-block-443", Action::kBlock, std::nullopt,
                        std::nullopt, Protocol::kTcp, 443, std::nullopt,
                        std::nullopt});
    canary.AddRule(Rule{"allow-corp-https", Action::kAllow, "10.0.0.0/8",
                        "10.0.0.0/8", Protocol::kTcp, 443, std::nullopt,
                        std::nullopt});
    std::cout << "canary divergences (shadow, not enforced): "
              << engine.CanaryDivergences(canary, packets) << "\n";
    std::cout << "recent traces:\n";
    for (const std::string& line : snap.recent_traces) std::cout << "  " << line << "\n";
    return 0;
}
