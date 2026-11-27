package com.dharma.banking.gateway;

import static org.hamcrest.Matchers.is;
import static org.hamcrest.Matchers.notNullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = "app.rate-limit.per-minute=5")
@AutoConfigureMockMvc
class GatewayFiltersTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void requestIdIsEchoedWhenProvided() throws Exception {
        mockMvc.perform(get("/ops/health")
                        .header("X-Request-Id", "trace-123")
                        .header("X-Client-Id", "echo-client"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-Id", "trace-123"));
    }

    @Test
    void requestIdIsGeneratedWhenMissing() throws Exception {
        mockMvc.perform(get("/ops/health").header("X-Client-Id", "gen-client"))
                .andExpect(status().isOk())
                .andExpect(header().exists("X-Request-Id"));
    }

    @Test
    void rateLimitReturns429AfterCapacity() throws Exception {
        for (int i = 0; i < 5; i++) {
            mockMvc.perform(get("/ops/health").header("X-Client-Id", "limited-client"))
                    .andExpect(status().isOk());
        }
        mockMvc.perform(get("/ops/health").header("X-Client-Id", "limited-client"))
                .andExpect(status().isTooManyRequests())
                .andExpect(jsonPath("$.error", is("Too many requests")));
    }

    @Test
    void healthIsUpAndMetricsCountRequests() throws Exception {
        mockMvc.perform(get("/ops/health").header("X-Client-Id", "metrics-client"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status", is("UP")));
        mockMvc.perform(get("/ops/metrics").header("X-Client-Id", "metrics-client"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalRequests", notNullValue()));
    }
}
