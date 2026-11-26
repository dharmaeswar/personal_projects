cmake_minimum_required(VERSION 3.16)
project(medical_device_software_validator CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

add_library(meddev
  src/crc16.cpp
  src/telemetry.cpp
  src/parameters.cpp
  src/alarms.cpp
  src/defects.cpp
)
target_include_directories(meddev PUBLIC src)
target_compile_options(meddev PRIVATE -Wall -Wextra -Werror)

add_executable(meddev_demo src/main.cpp)
target_link_libraries(meddev_demo PRIVATE meddev)

add_executable(meddev_tests tests/test_main.cpp)
target_link_libraries(meddev_tests PRIVATE meddev)
target_compile_options(meddev_tests PRIVATE -Wall -Wextra -Werror)

enable_testing()
add_test(NAME meddev_tests COMMAND meddev_tests)
