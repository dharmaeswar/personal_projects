# Medical Device Software Validator (C++17)

A small, dependency-free C++ validation library for surgical-device software
components: telemetry frame integrity, parameter range checks, threshold
alarms with hysteresis, and defect tracking. Built as a role project for a
Senior Software Engineer (C++) role at Stryker (medical devices, MedSurg /
Neurotechnology / Orthopaedics), whose posting asks for strong C++,
object-oriented design, production-level software development, integrating
complex systems, unit tests, code reviews, Agile/Scrum and SAFe, and defect
management through Jira.

## What it does

- `src/telemetry.{h,cpp}` — binary telemetry frame codec (device id, sequence,
  int16 readings, CRC-16/CCITT). The decoder rejects short frames, bad CRCs,
  length mismatches and out-of-order sequences, so a corrupted or replayed
  frame never reaches the parameter checks.
- `src/parameters.{h,cpp}` — safe/warning operating bands per device parameter
  (drill speed, irrigation flow, tip temperature). Readings are OK, WARNING or
  FAIL; a FAIL must open a defect, never silently pass.
- `src/alarms.{h,cpp}` — threshold alarms with hysteresis and latching: an
  alarm trips at the threshold and stays active until the reading falls below
  threshold minus hysteresis, so a noisy signal at the limit cannot flap it.
- `src/defects.{h,cpp}` — defect tracker (the Jira-side record): open/resolve
  defects with severities and report open counts per severity.
- `src/main.cpp` — demo: a scripted 6-frame session with one frame corrupted
  in transit; prints the per-frame validation report and open-defect count.

## Build and test

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
ctest --test-dir build --output-on-failure
./build/meddev_demo
```

Or without CMake:

```sh
g++ -std=c++17 -Wall -Wextra -I src src/*.cpp tests/test_main.cpp -o meddev_tests
./meddev_tests
g++ -std=c++17 -Wall -Wextra -I src src/*.cpp -o meddev_demo
./meddev_demo
```

## Test results

37 checks, 0 failures: CRC-16 known vector (`"123456789"` -> `0x29B1`),
telemetry round trip (including negative and empty readings), rejection of
corrupted / out-of-order / truncated frames, parameter band edges, alarm
latching and hysteresis, defect open/resolve/count behaviour.

## Demo result

6 frames: 5 accepted, 1 rejected (corrupted frame seq 4, bad CRC; the link
resyncs to the next sequence). All accepted readings are inside their safe
bands and the temperature alarm never trips. Open defects: 1 (warning
severity, the rejected frame). Exit code 1 — the run reports failure while
a defect is open, by design.

## Honest limits

All telemetry is synthetic and seeded; the parameter bands, alarm thresholds
and hysteresis values are chosen constants, not a real device's limits. There
is no Qt/QML user interface, no Jama requirements link and no connection to a
real Stryker device or codebase — the project shows the C++, validation,
defect-tracking and test discipline the role asks for, in working code with
tests.
