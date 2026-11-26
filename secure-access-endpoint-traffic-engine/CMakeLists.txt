cmake_minimum_required(VERSION 3.14)
project(secure_access_endpoint_traffic_engine CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_compile_options(-Wall -Wextra)

add_library(traffic_engine src/packet.cpp src/engine.cpp src/diagnostics.cpp)
target_include_directories(traffic_engine PUBLIC include)

add_executable(traffic_engine_tests tests/test_main.cpp)
target_link_libraries(traffic_engine_tests PRIVATE traffic_engine)

add_executable(traffic_engine_demo run_demo.cpp)
target_link_libraries(traffic_engine_demo PRIVATE traffic_engine)
