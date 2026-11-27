package com.dharma.banking.gateway;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

/** Registers the request-context filter first, then the rate-limit filter, for every route. */
@Configuration
public class GatewayConfig {
    @Bean
    public RequestMetrics requestMetrics() {
        return new RequestMetrics();
    }

    @Bean
    public RateLimiter rateLimiter(@Value("${app.rate-limit.per-minute:100}") int maxPerMinute) {
        return new RateLimiter(maxPerMinute);
    }

    @Bean
    public FilterRegistrationBean<RequestContextFilter> apiRequestContextFilter(RequestMetrics metrics) {
        FilterRegistrationBean<RequestContextFilter> bean =
                new FilterRegistrationBean<>(new RequestContextFilter(metrics));
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return bean;
    }

    @Bean
    public FilterRegistrationBean<RateLimitFilter> apiRateLimitFilter(RateLimiter limiter, ObjectMapper mapper) {
        FilterRegistrationBean<RateLimitFilter> bean =
                new FilterRegistrationBean<>(new RateLimitFilter(limiter, mapper));
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE + 1);
        return bean;
    }
}
