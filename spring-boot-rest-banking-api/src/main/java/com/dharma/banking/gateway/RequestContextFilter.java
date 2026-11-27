package com.dharma.banking.gateway;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Request-context filter: propagates or generates an X-Request-Id, records per-route
 * counts and latency, and logs one structured line per request for debugging.
 */
public class RequestContextFilter extends OncePerRequestFilter {
    public static final String REQUEST_ID_HEADER = "X-Request-Id";
    private static final Logger log = LoggerFactory.getLogger(RequestContextFilter.class);
    private final RequestMetrics metrics;

    public RequestContextFilter(RequestMetrics metrics) {
        this.metrics = metrics;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        String requestId = request.getHeader(REQUEST_ID_HEADER);
        if (requestId == null || requestId.isBlank()) {
            requestId = UUID.randomUUID().toString();
        }
        response.setHeader(REQUEST_ID_HEADER, requestId);
        long start = System.currentTimeMillis();
        try {
            chain.doFilter(request, response);
        } finally {
            long latency = System.currentTimeMillis() - start;
            metrics.record(request.getMethod(), request.getRequestURI(), response.getStatus(), latency);
            log.info("method={} path={} status={} latency_ms={} request_id={}",
                    request.getMethod(), request.getRequestURI(), response.getStatus(), latency, requestId);
        }
    }
}
