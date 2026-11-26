CXX ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -O2 -Iinclude
SRC = src/packet.cpp src/engine.cpp src/diagnostics.cpp

all: build/traffic_engine_tests build/traffic_engine_demo

build/traffic_engine_tests: $(SRC) tests/test_main.cpp
	mkdir -p build
	$(CXX) $(CXXFLAGS) $(SRC) tests/test_main.cpp -o $@

build/traffic_engine_demo: $(SRC) run_demo.cpp
	mkdir -p build
	$(CXX) $(CXXFLAGS) $(SRC) run_demo.cpp -o $@

test: build/traffic_engine_tests
	./build/traffic_engine_tests

demo: build/traffic_engine_demo
	./build/traffic_engine_demo

clean:
	rm -rf build

.PHONY: all test demo clean
