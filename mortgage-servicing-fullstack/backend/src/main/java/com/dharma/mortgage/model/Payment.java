package com.dharma.mortgage.model;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;

/** One borrower payment, split into principal, interest and escrow portions. */
public class Payment {
    private final String id;
    private final String loanId;
    private final BigDecimal amount;
    private final LocalDate paymentDate;
    private final BigDecimal principalPortion;
    private final BigDecimal interestPortion;
    private final BigDecimal escrowPortion;
    private final String idempotencyKey;
    private final BigDecimal remainingPrincipalAfter;

    public Payment(String loanId, BigDecimal amount, LocalDate paymentDate,
                   BigDecimal principalPortion, BigDecimal interestPortion,
                   BigDecimal escrowPortion, String idempotencyKey,
                   BigDecimal remainingPrincipalAfter) {
        this.id = UUID.randomUUID().toString();
        this.loanId = loanId;
        this.amount = amount;
        this.paymentDate = paymentDate;
        this.principalPortion = principalPortion;
        this.interestPortion = interestPortion;
        this.escrowPortion = escrowPortion;
        this.idempotencyKey = idempotencyKey;
        this.remainingPrincipalAfter = remainingPrincipalAfter;
    }

    public String getId() { return id; }
    public String getLoanId() { return loanId; }
    public BigDecimal getAmount() { return amount; }
    public LocalDate getPaymentDate() { return paymentDate; }
    public BigDecimal getPrincipalPortion() { return principalPortion; }
    public BigDecimal getInterestPortion() { return interestPortion; }
    public BigDecimal getEscrowPortion() { return escrowPortion; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public BigDecimal getRemainingPrincipalAfter() { return remainingPrincipalAfter; }
}
