package com.dharma.banking.service;

import java.math.BigDecimal;

public class InsufficientFundsException extends RuntimeException {
    public InsufficientFundsException(String accountId, BigDecimal balance, BigDecimal requested) {
        super("Account " + accountId + " has balance " + balance
                + " which is less than requested " + requested);
    }
}
