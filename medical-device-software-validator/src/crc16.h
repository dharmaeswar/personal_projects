// CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) for telemetry frame integrity.
#pragma once
#include <cstddef>
#include <cstdint>

namespace meddev {

std::uint16_t crc16_ccitt(const std::uint8_t* data, std::size_t length);

}  // namespace meddev
