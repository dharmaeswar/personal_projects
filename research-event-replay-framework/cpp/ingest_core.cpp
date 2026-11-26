// ingest_core.cpp — throughput-critical tick ingest core (C++17).
//
// Reads the plain-text tick CSV the Python ingest module writes and
// reports per-symbol counts, total volume, and the min/max price seen.
// This is the shape of the modern C++ ingest core in a research platform:
// a tight, allocation-light parse loop over raw exchange data. It reads
// only the synthetic demo CSVs this project generates; it never touches
// a live feed.

#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>

struct SymbolStats {
    std::uint64_t ticks = 0;
    std::uint64_t volume = 0;
    double min_price = 0.0;
    double max_price = 0.0;
};

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: ingest_core <ticks.csv>\n";
        return 2;
    }
    std::ifstream in(argv[1]);
    if (!in) {
        std::cerr << "cannot open " << argv[1] << "\n";
        return 1;
    }
    std::string line;
    if (!std::getline(in, line)) return 1;  // header
    std::map<std::string, SymbolStats> stats;
    std::uint64_t rows = 0;
    std::uint64_t bad = 0;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::istringstream ss(line);
        std::string ts, symbol, side, price_s, size_s;
        if (!std::getline(ss, ts, ',') || !std::getline(ss, symbol, ',') ||
            !std::getline(ss, side, ',') || !std::getline(ss, price_s, ',') ||
            !std::getline(ss, size_s, ',')) {
            ++bad;
            continue;
        }
        double price = 0.0;
        std::uint64_t size = 0;
        try {
            price = std::stod(price_s);
            size = std::stoull(size_s);
        } catch (...) {
            ++bad;
            continue;
        }
        if (price <= 0.0 || size == 0) {
            ++bad;
            continue;
        }
        auto& s = stats[symbol];
        if (s.ticks == 0) {
            s.min_price = price;
            s.max_price = price;
        } else {
            if (price < s.min_price) s.min_price = price;
            if (price > s.max_price) s.max_price = price;
        }
        ++s.ticks;
        s.volume += size;
        ++rows;
    }
    std::cout << "rows=" << rows << " bad=" << bad << "\n";
    for (const auto& [symbol, s] : stats) {
        std::cout << symbol << " ticks=" << s.ticks << " volume=" << s.volume
                  << " min=" << s.min_price << " max=" << s.max_price << "\n";
    }
    return bad == 0 ? 0 : 1;
}
