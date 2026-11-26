// CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) for telemetry frame integrity.
#include "crc16.h"

namespace meddev {

std::uint16_t crc16_ccitt(const std::uint8_t* data, std::size_t length) {
    std::uint16_t crc = 0xFFFF;
    for (std::size_t i = 0; i < length; ++i) {
        crc ^= static_cast<std::uint16_t>(data[i]) << 8;
        for (int bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x8000) != 0 ? static_cast<std::uint16_t>((crc << 1) ^ 0x1021)
                                      : static_cast<std::uint16_t>(crc << 1);
        }
    }
    return crc;
}

}  // namespace meddev
