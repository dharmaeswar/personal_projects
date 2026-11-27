# Secure Access Endpoint Traffic Engine

A portfolio project for a Senior Software Engineer, C++ (Global Secure
Access Client) application at Microsoft. It builds the kind of component
the role asks for: a secure endpoint traffic-handling engine that
classifies outbound packets, enforces an ordered allow/block policy,
tracks connection state in a bounded table, processes traffic
concurrently, and records diagnostics — in modern C++17, standard
library only, no OS-specific or kernel code.

All traffic, hosts, domains, and policies are synthetic examples. Nothing
here describes a real Microsoft system, real customer traffic, or a real
enterprise deployment. This is not a Windows driver, not a WFP/NDIS
component, and not a kernel-mode component: it models the endpoint
decision logic (policy evaluation, connection state, concurrency,
diagnostics, safe rollout) in portable user-mode C++ so the logic can be
built, tested, and reviewed on any machine.

## What it does

- **Packet model** (`include/traffic_engine.h`, `src/packet.cpp`) —
  IPv4 5-tuple (source/destination address and port, TCP/UDP) plus DNS
  name and TLS SNI, with bounds-checked parsing. Malformed packets
  (bad address, oversized payload, impossible length) are quarantined,
  never passed to the policy engine.
- **Policy engine** (`src/engine.cpp`) — ordered first-match rules over
  CIDR ranges, protocol, destination port, DNS name, and TLS SNI, with a
  default-deny. Every decision names the rule that fired, so a blocked
  connection is explainable in one line.
- **Connection state** (`src/engine.cpp`) — a bounded connection table
  (fixed capacity, oldest-entry eviction, no unbounded growth) keyed by
  5-tuple, with per-connection packet/byte counts and last-seen order.
- **Concurrency** (`src/engine.cpp`) — a worker thread pool over a
  mutex-guarded queue; atomic counters for processed / allowed /
  blocked / quarantined / evicted, so totals stay exact under threads.
- **Diagnostics** (`src/diagnostics.cpp`) — an append-only structured
  trace log, per-packet capture records (sequence, 5-tuple, decision,
  rule), and a snapshot (counters, table size, recent traces) of the
  kind a crash dump or support bundle would carry.
- **Safe rollout** (`src/engine.cpp`) — a canary policy runs in shadow
  mode: the candidate policy is evaluated alongside the active one and
  divergences are counted, but the candidate never enforces a decision
  until it is promoted.

## Build and test

```sh
cmake -S . -B build && cmake --build build
./build/traffic_engine_tests    # 47 assertions, all must pass
./build/traffic_engine_demo     # seeded synthetic traffic, printed summary
```

Or without CMake: `make` (uses `g++ -std=c++17 -Wall -Wextra`).

## Demo

`run_demo.cpp` seeds 240 synthetic packets (corporate allow-listed
traffic, blocked external destinations, DNS and TLS-SNI cases, 5 planted
malformed packets), runs them through a 4-worker engine, then evaluates
a canary policy in shadow mode. Expected output: 240 processed, 144
allowed, 72 blocked, 24 quarantined, and 144 canary divergences (the
canary would flip the 120 corporate-HTTPS and 24 DNS allows to blocks).

## Honest limits

- Portable user-mode C++ only. No Windows internals, kernel-mode code,
  device drivers, WFP, or NDIS — those are listed as gaps in the
  application notes, not claimed here.
- The "network" is in-memory synthetic packets, not a real NIC, socket,
  or VPN tunnel; there is no real TLS handshake and no real DNS
  resolution — SNI and DNS names are fields on synthetic packets.
- Concurrency is a thread pool over an in-process queue, not a
  production dispatcher; performance is measured in-process, not
  against a production throughput or latency target.
- The policy is a small ordered rule list, not a cloud-delivered
  enterprise policy service; there is no real authentication, identity,
  or cloud integration.
