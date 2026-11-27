package com.dharma.mortgage.service;

import java.math.BigDecimal;

public class InvalidPaymentException extends RuntimeException {
    public InvalidPaymentException(BigDecimal amount, BigDecimal minimumDue) {
        super("Payment " + amount + " is below the minimum due " + minimumDue
                + " (interest + escrow for this month)");
    }
}
