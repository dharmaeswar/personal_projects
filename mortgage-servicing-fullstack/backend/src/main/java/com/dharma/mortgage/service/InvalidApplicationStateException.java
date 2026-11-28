package com.dharma.mortgage.service;

import com.dharma.mortgage.model.ApplicationStatus;

public class InvalidApplicationStateException extends RuntimeException {
    public InvalidApplicationStateException(String applicationId, ApplicationStatus current,
            String attempted) {
        super("Application " + applicationId + " is " + current
                + " and cannot be moved to " + attempted);
    }
}
