// Telemetry frame codec for a surgical device link.
//
// Wire format (all multi-byte fields big-endian):
//   [device_id:1][sequence:2][reading_count:1][readings:2*count][crc16:2]
// The CRC covers everything before it. Decoders reject short frames, bad CRCs
// and out-of-order sequences so a corrupted or replayed frame never reaches
// the parameter checks downstream.
#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>

namespace meddev {

struct Frame {
    std::uint8_t device_id = 0;
    std::uint16_t sequence = 0;
    std::vector<std::int16_t> readings;
};

enum class DecodeError {
    kOk = 0,
    kTooShort,
    kBadCrc,
    kBadLength,
    kOutOfOrder,
};

struct DecodeResult {
    Frame frame;
    DecodeError error = DecodeError::kOk;
    bool ok() const { return error == DecodeError::kOk; }
};

// Serialises a frame, appending the CRC-16 of the header + payload.
std::vector<std::uint8_t> encode_frame(const Frame& frame);

// Decodes one frame. `expected_sequence` is the next sequence number the link
// expects; pass 0 to skip the ordering check (first frame of a session).
DecodeResult decode_frame(const std::uint8_t* data, std::size_t length,
                          std::uint16_t expected_sequence);

}  // namespace meddev
