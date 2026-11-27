package com.dharma.mortgage.dto;

import com.dharma.mortgage.model.Payment;
import java.math.BigDecimal;
import java.time.LocalDate;

public class PaymentResponse {
    private final String id;
    private final String loanId;
    private final BigDecimal amount;
    private final LocalDate paymentDate;
    private final BigDecimal principalPortion;
    private final BigDecimal interestPortion;
    private final BigDecimal escrowPortion;
    private final BigDecimal remainingPrincipalAfter;

    public PaymentResponse(Payment payment) {
        this.id = payment.getId();
        this.loanId = payment.getLoanId();
        this.amount = payment.getAmount();
        this.paymentDate = payment.getPaymentDate();
        this.principalPortion = payment.getPrincipalPortion();
        this.interestPortion = payment.getInterestPortion();
        this.escrowPortion = payment.getEscrowPortion();
        this.remainingPrincipalAfter = payment.getRemainingPrincipalAfter();
    }

    public String getId() { return id; }
    public String getLoanId() { return loanId; }
    public BigDecimal getAmount() { return amount; }
    public LocalDate getPaymentDate() { return paymentDate; }
    public BigDecimal getPrincipalPortion() { return principalPortion; }
    public BigDecimal getInterestPortion() { return interestPortion; }
    public BigDecimal getEscrowPortion() { return escrowPortion; }
    public BigDecimal getRemainingPrincipalAfter() { return remainingPrincipalAfter; }
}
