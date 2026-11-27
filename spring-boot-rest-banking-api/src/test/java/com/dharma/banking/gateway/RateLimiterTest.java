package com.dharma.banking.gateway;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class RateLimiterTest {
    @Test
    void allowsUpToCapacityThenBlocks() {
        RateLimiter limiter = new RateLimiter(3);
        assertTrue(limiter.tryAcquire("client-a"));
        assertTrue(limiter.tryAcquire("client-a"));
        assertTrue(limiter.tryAcquire("client-a"));
        assertFalse(limiter.tryAcquire("client-a"));
    }

    @Test
    void limitsArePerClient() {
        RateLimiter limiter = new RateLimiter(1);
        assertTrue(limiter.tryAcquire("client-a"));
        assertFalse(limiter.tryAcquire("client-a"));
        assertTrue(limiter.tryAcquire("client-b"));
    }
}
