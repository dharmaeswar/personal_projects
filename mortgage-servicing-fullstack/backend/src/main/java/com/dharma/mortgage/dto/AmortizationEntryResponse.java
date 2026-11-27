package com.dharma.mortgage.dto;

import com.dharma.mortgage.model.AmortizationEntry;
import java.math.BigDecimal;

public class AmortizationEntryResponse {
    private final int month;
    private final BigDecimal payment;
    private final BigDecimal principal;
    private final BigDecimal interest;
    private final BigDecimal escrow;
    private final BigDecimal remainingBalance;

    public AmortizationEntryResponse(AmortizationEntry entry) {
        this.month = entry.month();
        this.payment = entry.payment();
        this.principal = entry.principal();
        this.interest = entry.interest();
        this.escrow = entry.escrow();
        this.remainingBalance = entry.remainingBalance();
    }

    public int getMonth() { return month; }
    public BigDecimal getPayment() { return payment; }
    public BigDecimal getPrincipal() { return principal; }
    public BigDecimal getInterest() { return interest; }
    public BigDecimal getEscrow() { return escrow; }
    public BigDecimal getRemainingBalance() { return remainingBalance; }
}
