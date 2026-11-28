package com.dharma.mortgage.model;

/** Lifecycle of a borrower home-lending application, from intake to funding. */
public enum ApplicationStatus {
    STARTED,
    SUBMITTED,
    APPROVED,
    CONDITIONAL,
    DENIED,
    CLOSING,
    FUNDED
}
