#!/bin/sh
# Build, test and demo the AML surveillance data pipeline.
# Plain JDK only (Java 17+): no Maven, Gradle or third-party jars.
set -e
cd "$(dirname "$0")"
rm -rf out
mkdir -p out
javac -encoding UTF-8 -d out $(find src/main/java src/test/java -name '*.java')
echo "--- tests ---"
java -ea -cp out aml.AmlPipelineTest
echo "--- demo run (batch + micro-batch) ---"
java -cp out aml.Pipeline
