#include <cassert>
#include <iostream>
#include <string>
#include <vector>

#include "traffic_engine.h"

using namespace gsa;

static int g_checks = 0;
static int g_failures = 0;

#define CHECK(cond)                                                     \
    do {                                                                \
        ++g_checks;                                                     \
        if (!(cond)) {                                                  \
            ++g_failures;                                               \
            std::cerr << "FAIL line " << __LINE__ << ": " #cond "\n";  \
        }                                                               \
    } while (0)

static Packet Pkt(const std::string& dst, std::uint16_t dport, Protocol proto,
                  const std::string& sni = "", const std::string& dns = "",
                  std::uint64_t seq = 1, std::size_t bytes = 100) {
    Packet p;
    p.src_ip = "10.1.2.3";
    p.dst_ip = dst;
    p.src_port = 50000;
    p.dst_port = dport;
    p.protocol = proto;
    p.tls_sni = sni;
    p.dns_name = dns;
    p.seq = seq;
    p.payload_bytes = bytes;
    return p;
}

static Policy CorporatePolicy() {
    Policy policy;
    policy.AddRule(Rule{"allow-corp-https", Action::kAllow,
                        "10.0.0.0/8", "10.0.0.0/8", Protocol::kTcp, 443,
                        std::nullopt, std::nullopt});
    policy.AddRule(Rule{"allow-corp-dns", Action::kAllow, "10.0.0.0/8",
                        std::nullopt, Protocol::kUdp, 53, std::nullopt,
                        std::nullopt});
    policy.AddRule(Rule{"block-bad-sni", Action::kBlock, std::nullopt,
                        std::nullopt, Protocol::kTcp, 443, std::nullopt,
                        "evil.example.com"});
    policy.AddRule(Rule{"allow-trusted-sni", Action::kAllow, std::nullopt,
                        std::nullopt, Protocol::kTcp, 443, std::nullopt,
                        "login.corp.example"});
    return policy;
}

int main() {
    // IPv4 parsing and CIDR matching (bounds-checked, malformed rejected).
    std::uint32_t addr = 0;
    CHECK(ParseIpv4("10.1.2.3", &addr));
    CHECK(addr == 0x0A010203u);
    CHECK(!ParseIpv4("999.1.2.3", &addr));
    CHECK(!ParseIpv4("10.1.2", &addr));
    CHECK(!ParseIpv4("10.1.2.3.4", &addr));
    CHECK(!ParseIpv4("10.1.2.x", &addr));
    CHECK(!ParseIpv4("", &addr));
    CHECK(!ParseIpv4("10..2.3", &addr));
    CHECK(CidrContains("10.0.0.0/8", "10.200.3.4"));
    CHECK(!CidrContains("10.0.0.0/8", "192.168.1.1"));
    CHECK(CidrContains("192.168.1.0/24", "192.168.1.200"));
    CHECK(!CidrContains("192.168.1.0/24", "192.168.2.1"));
    CHECK(CidrContains("0.0.0.0/0", "203.0.113.9"));
    CHECK(!CidrContains("10.0.0.0/33", "10.0.0.1"));
    CHECK(!CidrContains("not-a-cidr", "10.0.0.1"));

    // Policy: first match wins; default-deny when nothing matches.
    Policy policy = CorporatePolicy();
    CHECK(policy.RuleCount() == 4);
    Decision d = policy.Evaluate(Pkt("10.9.8.7", 443, Protocol::kTcp));
    CHECK(d.kind == DecisionKind::kAllowed && d.rule_name == "allow-corp-https");
    d = policy.Evaluate(Pkt("10.9.8.7", 53, Protocol::kUdp));
    CHECK(d.kind == DecisionKind::kAllowed && d.rule_name == "allow-corp-dns");
    d = policy.Evaluate(Pkt("203.0.113.9", 443, Protocol::kTcp, "evil.example.com"));
    CHECK(d.kind == DecisionKind::kBlocked && d.rule_name == "block-bad-sni");
    d = policy.Evaluate(Pkt("203.0.113.9", 443, Protocol::kTcp, "login.corp.example"));
    CHECK(d.kind == DecisionKind::kAllowed && d.rule_name == "allow-trusted-sni");
    d = policy.Evaluate(Pkt("203.0.113.9", 80, Protocol::kTcp));
    CHECK(d.kind == DecisionKind::kBlocked && d.rule_name == "default-deny");
    // Rule order matters: the block rule above precedes the trusted-SNI allow.
    d = policy.Evaluate(Pkt("203.0.113.9", 443, Protocol::kTcp, "evil.example.com"));
    CHECK(d.rule_name == "block-bad-sni");

    // DNS suffix rule.
    Policy dns_policy;
    dns_policy.AddRule(Rule{"allow-corp-dns-name", Action::kAllow, std::nullopt,
                            std::nullopt, Protocol::kUdp, 53, ".corp.example",
                            std::nullopt});
    d = dns_policy.Evaluate(Pkt("8.8.8.8", 53, Protocol::kUdp, "", "host.corp.example"));
    CHECK(d.kind == DecisionKind::kAllowed);
    d = dns_policy.Evaluate(Pkt("8.8.8.8", 53, Protocol::kUdp, "", "host.other.example"));
    CHECK(d.kind == DecisionKind::kBlocked);

    // Engine: malformed packets are quarantined, never policy-evaluated.
    Engine engine(CorporatePolicy());
    Packet bad_ip = Pkt("10.9.8.7", 443, Protocol::kTcp);
    bad_ip.dst_ip = "not-an-ip";
    d = engine.Process(bad_ip);
    CHECK(d.kind == DecisionKind::kQuarantined && d.rule_name == "malformed");
    Packet huge = Pkt("10.9.8.7", 443, Protocol::kTcp);
    huge.payload_bytes = 2 * 1024 * 1024;
    d = engine.Process(huge);
    CHECK(d.kind == DecisionKind::kQuarantined);
    Packet unknown = Pkt("10.9.8.7", 443, Protocol::kUnknown);
    d = engine.Process(unknown);
    CHECK(d.kind == DecisionKind::kQuarantined);

    // Engine: allowed flows create one connection entry; repeats update it.
    d = engine.Process(Pkt("10.9.8.7", 443, Protocol::kTcp, "", "", 10, 500));
    CHECK(d.kind == DecisionKind::kAllowed);
    CHECK(engine.ConnectionCount() == 1);
    d = engine.Process(Pkt("10.9.8.7", 443, Protocol::kTcp, "", "", 11, 700));
    CHECK(d.kind == DecisionKind::kAllowed);
    CHECK(engine.ConnectionCount() == 1);  // same 5-tuple, same connection
    d = engine.Process(Pkt("203.0.113.9", 80, Protocol::kTcp, "", "", 12));
    CHECK(d.kind == DecisionKind::kBlocked);
    CHECK(engine.ConnectionCount() == 1);  // blocked flows open no connection

    Snapshot snap = engine.TakeSnapshot();
    CHECK(snap.processed == 6);
    CHECK(snap.quarantined == 3);
    CHECK(snap.allowed == 2);
    CHECK(snap.blocked == 1);
    CHECK(snap.connections == 1);
    CHECK(!snap.recent_traces.empty());

    // Bounded table: flood with distinct flows, size never exceeds the cap.
    Engine flood(CorporatePolicy());
    for (std::uint64_t i = 0; i < Engine::kMaxConnections + 50; ++i) {
        Packet p = Pkt("10.9.8.7", 443, Protocol::kTcp, "", "", i, 10);
        p.src_port = static_cast<std::uint16_t>(1000 + (i % 60000));
        flood.Process(p);
    }
    CHECK(flood.ConnectionCount() == Engine::kMaxConnections);
    CHECK(flood.TakeSnapshot().evicted == 50);

    // Concurrency: totals stay exact under 4 workers.
    Engine concurrent(CorporatePolicy());
    std::vector<Packet> batch;
    for (std::uint64_t i = 0; i < 400; ++i) {
        Packet p = (i % 2 == 0) ? Pkt("10.9.8.7", 443, Protocol::kTcp, "", "", i)
                                : Pkt("203.0.113.9", 80, Protocol::kTcp, "", "", i);
        batch.push_back(p);
    }
    concurrent.RunConcurrent(batch, 4);
    Snapshot cs = concurrent.TakeSnapshot();
    CHECK(cs.processed == 400);
    CHECK(cs.allowed == 200);
    CHECK(cs.blocked == 200);
    CHECK(cs.quarantined == 0);

    // Canary shadow mode: identical policy diverges 0 times; a stricter
    // candidate diverges exactly on the flows it would newly block.
    Policy canary = CorporatePolicy();
    canary.AddRule(Rule{"block-all-https", Action::kBlock, std::nullopt,
                        std::nullopt, Protocol::kTcp, 443, std::nullopt,
                        std::nullopt});
    // Note: appended last, so it never fires before the allow rules.
    CHECK(engine.CanaryDivergences(canary, batch) == 0);
    Policy strict;
    strict.AddRule(Rule{"block-all", Action::kBlock, std::nullopt, std::nullopt,
                        std::nullopt, std::nullopt, std::nullopt, std::nullopt});
    CHECK(engine.CanaryDivergences(strict, batch) == 200);  // the 200 allowed

    std::cout << "checks=" << g_checks << " failures=" << g_failures << "\n";
    return g_failures == 0 ? 0 : 1;
}
