package com.dharma.mortgage.service;

public class LoanNotFoundException extends RuntimeException {
    public LoanNotFoundException(String loanId) {
        super("Loan not found: " + loanId);
    }
}
