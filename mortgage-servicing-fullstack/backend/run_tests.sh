#!/usr/bin/env bash
# Runs the backend test suite. Requires Java 17+ and Maven 3.9+ on PATH.
# Mockito's inline mock maker self-attaches an agent through the JVM temp dir;
# point it at a project-local dir so a full system /tmp cannot break the run.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .tmp
mvn -B test -DargLine="-Djava.io.tmpdir=$PWD/.tmp"
