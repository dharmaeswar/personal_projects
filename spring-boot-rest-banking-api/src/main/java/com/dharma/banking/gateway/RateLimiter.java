package com.dharma.banking.gateway;

import java.util.concurrent.ConcurrentHashMap;

/** Per-client token-bucket rate limiter, refilled continuously over a one-minute window. */
public class RateLimiter {
    private final int maxRequestsPerMinute;
    private final ConcurrentHashMap<String, TokenBucket> buckets = new ConcurrentHashMap<>();

    public RateLimiter(int maxRequestsPerMinute) {
        if (maxRequestsPerMinute < 1) {
            throw new IllegalArgumentException("maxRequestsPerMinute must be >= 1");
        }
        this.maxRequestsPerMinute = maxRequestsPerMinute;
    }

    public boolean tryAcquire(String key) {
        return buckets.computeIfAbsent(key, k -> new TokenBucket(maxRequestsPerMinute)).tryAcquire();
    }

    private static class TokenBucket {
        private final int capacity;
        private double tokens;
        private long lastRefillNanos;

        TokenBucket(int capacity) {
            this.capacity = capacity;
            this.tokens = capacity;
            this.lastRefillNanos = System.nanoTime();
        }

        synchronized boolean tryAcquire() {
            long now = System.nanoTime();
            double elapsedMinutes = (now - lastRefillNanos) / 60_000_000_000.0;
            tokens = Math.min(capacity, tokens + elapsedMinutes * capacity);
            lastRefillNanos = now;
            if (tokens < 1.0) {
                return false;
            }
            tokens -= 1.0;
            return true;
        }
    }
}
