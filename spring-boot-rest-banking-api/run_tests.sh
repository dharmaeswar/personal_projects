#!/usr/bin/env bash
# Runs the full test suite for the Spring Boot REST Banking API.
# Requires Java 17+ and Maven 3.9+ on PATH.
set -euo pipefail
cd "$(dirname "$0")"
mvn -B test
