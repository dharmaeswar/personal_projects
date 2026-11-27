package com.dharma.banking.gateway;

import com.dharma.banking.dto.ErrorResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

/** Rejects traffic over the per-client rate limit with HTTP 429 and a JSON error body. */
public class RateLimitFilter extends OncePerRequestFilter {
    public static final String CLIENT_ID_HEADER = "X-Client-Id";
    private final RateLimiter limiter;
    private final ObjectMapper mapper;

    public RateLimitFilter(RateLimiter limiter, ObjectMapper mapper) {
        this.limiter = limiter;
        this.mapper = mapper;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        String key = request.getHeader(CLIENT_ID_HEADER);
        if (key == null || key.isBlank()) {
            key = request.getRemoteAddr();
        }
        if (!limiter.tryAcquire(key)) {
            response.setStatus(HttpStatus.TOO_MANY_REQUESTS.value());
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            ErrorResponse body = new ErrorResponse(HttpStatus.TOO_MANY_REQUESTS.value(),
                    "Too many requests",
                    List.of("Rate limit exceeded for this client; retry after a minute."));
            mapper.writeValue(response.getWriter(), body);
            return;
        }
        chain.doFilter(request, response);
    }
}
