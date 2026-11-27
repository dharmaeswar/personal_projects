package com.dharma.banking.ops;

import com.dharma.banking.gateway.RequestMetrics;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Health and request-metrics endpoints for deployment validation and operations. */
@RestController
@RequestMapping("/ops")
public class OpsController {
    private final RequestMetrics metrics;

    public OpsController(RequestMetrics metrics) {
        this.metrics = metrics;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "UP");
    }

    @GetMapping("/metrics")
    public Map<String, Object> metrics() {
        return metrics.snapshot();
    }
}
