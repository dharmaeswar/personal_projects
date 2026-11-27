package com.dharma.mortgage.model;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

/**
 * A mortgage loan being serviced. Money is always BigDecimal, scale 2 — never double.
 * The remaining principal only moves inside {@link #applyPayment}, which the caller
 * locks, so concurrent payments on one loan cannot corrupt the balance.
 */
public class Loan {
    private final String id;
    private final String borrowerName;
    private final BigDecimal originalPrincipal;
    private final BigDecimal annualRatePct;
    private final int termMonths;
    private final LocalDate startDate;
    private final BigDecimal escrowMonthly;
    private BigDecimal remainingPrincipal;
    private BigDecimal escrowBalance;
    private LocalDate lastPaymentDate;
    private LoanStatus status;
    private final List<Payment> payments = new ArrayList<>();

    public Loan(String borrowerName, BigDecimal originalPrincipal, BigDecimal annualRatePct,
                int termMonths, LocalDate startDate, BigDecimal escrowMonthly) {
        this.id = UUID.randomUUID().toString();
        this.borrowerName = borrowerName;
        this.originalPrincipal = originalPrincipal.setScale(2, RoundingMode.HALF_UP);
        this.annualRatePct = annualRatePct.setScale(4, RoundingMode.HALF_UP);
        this.termMonths = termMonths;
        this.startDate = startDate;
        this.escrowMonthly = escrowMonthly.setScale(2, RoundingMode.HALF_UP);
        this.remainingPrincipal = this.originalPrincipal;
        this.escrowBalance = BigDecimal.ZERO.setScale(2);
        this.status = LoanStatus.CURRENT;
    }

    public String getId() { return id; }
    public String getBorrowerName() { return borrowerName; }
    public BigDecimal getOriginalPrincipal() { return originalPrincipal; }
    public BigDecimal getAnnualRatePct() { return annualRatePct; }
    public int getTermMonths() { return termMonths; }
    public LocalDate getStartDate() { return startDate; }
    public BigDecimal getEscrowMonthly() { return escrowMonthly; }
    public synchronized BigDecimal getRemainingPrincipal() { return remainingPrincipal; }
    public synchronized BigDecimal getEscrowBalance() { return escrowBalance; }
    public synchronized LocalDate getLastPaymentDate() { return lastPaymentDate; }
    public synchronized LoanStatus getStatus() { return status; }
    public synchronized List<Payment> getPayments() {
        return Collections.unmodifiableList(new ArrayList<>(payments));
    }

    /** Monthly P&amp;I payment from the standard amortization formula. */
    public BigDecimal monthlyPayment() {
        return Amortization.monthlyPayment(originalPrincipal, annualRatePct, termMonths);
    }

    /** Interest due on the current balance for one month. */
    public BigDecimal monthlyInterest() {
        return Amortization.monthlyInterest(remainingPrincipal, annualRatePct);
    }

    /**
     * Applies a payment split into interest, principal and escrow. The caller must
     * hold the lock and must have checked the amount covers interest + escrow.
     * Any amount above interest + escrow + remaining principal is refused by the
     * service; extra above the scheduled split goes to principal.
     */
    public synchronized Payment applyPayment(BigDecimal amount, LocalDate paymentDate,
                                             String idempotencyKey) {
        BigDecimal interest = monthlyInterest();
        BigDecimal escrow = escrowMonthly;
        BigDecimal principal = amount.subtract(interest).subtract(escrow)
                .setScale(2, RoundingMode.HALF_UP);
        if (principal.compareTo(remainingPrincipal) > 0) {
            principal = remainingPrincipal;
        }
        remainingPrincipal = remainingPrincipal.subtract(principal)
                .setScale(2, RoundingMode.HALF_UP);
        escrowBalance = escrowBalance.add(escrow).setScale(2, RoundingMode.HALF_UP);
        lastPaymentDate = paymentDate;
        if (remainingPrincipal.compareTo(BigDecimal.ZERO) == 0) {
            status = LoanStatus.PAID_OFF;
        }
        Payment payment = new Payment(id, amount, paymentDate, principal, interest, escrow,
                idempotencyKey, remainingPrincipal);
        payments.add(payment);
        return payment;
    }

    /** Delinquent when no payment has landed within 30 days of the given date. */
    public synchronized boolean isDelinquent(LocalDate asOf) {
        if (status == LoanStatus.PAID_OFF) {
            return false;
        }
        LocalDate due = lastPaymentDate == null ? startDate : lastPaymentDate;
        return due.plusDays(30).isBefore(asOf);
    }

    public synchronized void markDelinquent() {
        if (status == LoanStatus.CURRENT) {
            status = LoanStatus.DELINQUENT;
        }
    }
}
