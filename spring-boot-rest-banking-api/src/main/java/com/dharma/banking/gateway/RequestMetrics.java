package com.dharma.banking.gateway;

import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/** In-memory request counters and latency totals for the /ops/metrics endpoint. */
public class RequestMetrics {
    private final ConcurrentHashMap<String, AtomicLong> counts = new ConcurrentHashMap<>();
    private final AtomicLong totalRequests = new AtomicLong();
    private final AtomicLong totalLatencyMs = new AtomicLong();

    public void record(String method, String path, int status, long latencyMs) {
        String key = method + " " + normalize(path) + " " + status;
        counts.computeIfAbsent(key, k -> new AtomicLong()).incrementAndGet();
        totalRequests.incrementAndGet();
        totalLatencyMs.addAndGet(latencyMs);
    }

    /** Collapse id-like path segments (UUIDs, long hex) so per-account URLs share one bucket. */
    static String normalize(String path) {
        return path.replaceAll("/[0-9a-fA-F-]{8,}(?=/|$)", "/{id}");
    }

    public Map<String, Object> snapshot() {
        Map<String, Long> byRoute = new TreeMap<>();
        counts.forEach((key, value) -> byRoute.put(key, value.get()));
        long total = totalRequests.get();
        Map<String, Object> out = new TreeMap<>();
        out.put("totalRequests", total);
        out.put("averageLatencyMs", total == 0 ? 0 : totalLatencyMs.get() / total);
        out.put("countsByRouteAndStatus", byRoute);
        return out;
    }

    public long totalRequests() {
        return totalRequests.get();
    }
}
