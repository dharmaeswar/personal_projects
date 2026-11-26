// Telemetry frame codec for a surgical device link.
#include "telemetry.h"

#include "crc16.h"

namespace meddev {

namespace {
constexpr std::size_t kHeaderSize = 4;  // device_id + sequence + count
constexpr std::size_t kCrcSize = 2;

void append_u16(std::vector<std::uint8_t>& out, std::uint16_t value) {
    out.push_back(static_cast<std::uint8_t>((value >> 8) & 0xFF));
    out.push_back(static_cast<std::uint8_t>(value & 0xFF));
}
}  // namespace

std::vector<std::uint8_t> encode_frame(const Frame& frame) {
    std::vector<std::uint8_t> out;
    out.reserve(kHeaderSize + frame.readings.size() * 2 + kCrcSize);
    out.push_back(frame.device_id);
    append_u16(out, frame.sequence);
    out.push_back(static_cast<std::uint8_t>(frame.readings.size()));
    for (std::int16_t reading : frame.readings) {
        append_u16(out, static_cast<std::uint16_t>(reading));
    }
    append_u16(out, crc16_ccitt(out.data(), out.size()));
    return out;
}

DecodeResult decode_frame(const std::uint8_t* data, std::size_t length,
                          std::uint16_t expected_sequence) {
    DecodeResult result;
    if (length < kHeaderSize + kCrcSize) {
        result.error = DecodeError::kTooShort;
        return result;
    }
    const std::uint16_t wire_crc =
        static_cast<std::uint16_t>((data[length - 2] << 8) | data[length - 1]);
    if (crc16_ccitt(data, length - kCrcSize) != wire_crc) {
        result.error = DecodeError::kBadCrc;
        return result;
    }
    const std::uint8_t count = data[3];
    if (length != kHeaderSize + static_cast<std::size_t>(count) * 2 + kCrcSize) {
        result.error = DecodeError::kBadLength;
        return result;
    }
    Frame frame;
    frame.device_id = data[0];
    frame.sequence =
        static_cast<std::uint16_t>((data[1] << 8) | data[2]);
    for (std::uint8_t i = 0; i < count; ++i) {
        const std::size_t off = kHeaderSize + static_cast<std::size_t>(i) * 2;
        frame.readings.push_back(static_cast<std::int16_t>(
            (data[off] << 8) | data[off + 1]));
    }
    result.frame = frame;
    if (expected_sequence != 0 && frame.sequence != expected_sequence) {
        result.error = DecodeError::kOutOfOrder;
        return result;
    }
    return result;
}

}  // namespace meddev
