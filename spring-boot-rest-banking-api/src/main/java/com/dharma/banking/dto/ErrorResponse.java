package com.dharma.banking.dto;

import java.time.Instant;
import java.util.List;

public class ErrorResponse {
    private final int status;
    private final String error;
    private final List<String> details;
    private final Instant timestamp;

    public ErrorResponse(int status, String error, List<String> details) {
        this.status = status;
        this.error = error;
        this.details = details;
        this.timestamp = Instant.now();
    }

    public int getStatus() { return status; }
    public String getError() { return error; }
    public List<String> getDetails() { return details; }
    public Instant getTimestamp() { return timestamp; }
}
