package com.dharma.mortgage.dto;

import com.dharma.mortgage.model.Loan;
import com.dharma.mortgage.model.LoanStatus;
import java.math.BigDecimal;
import java.time.LocalDate;

public class LoanResponse {
    private final String id;
    private final String borrowerName;
    private final BigDecimal originalPrincipal;
    private final BigDecimal remainingPrincipal;
    private final BigDecimal annualRatePct;
    private final int termMonths;
    private final LocalDate startDate;
    private final BigDecimal escrowMonthly;
    private final BigDecimal escrowBalance;
    private final BigDecimal monthlyPayment;
    private final LocalDate lastPaymentDate;
    private final LoanStatus status;

    public LoanResponse(Loan loan) {
        this.id = loan.getId();
        this.borrowerName = loan.getBorrowerName();
        this.originalPrincipal = loan.getOriginalPrincipal();
        this.remainingPrincipal = loan.getRemainingPrincipal();
        this.annualRatePct = loan.getAnnualRatePct();
        this.termMonths = loan.getTermMonths();
        this.startDate = loan.getStartDate();
        this.escrowMonthly = loan.getEscrowMonthly();
        this.escrowBalance = loan.getEscrowBalance();
        this.monthlyPayment = loan.monthlyPayment();
        this.lastPaymentDate = loan.getLastPaymentDate();
        this.status = loan.getStatus();
    }

    public String getId() { return id; }
    public String getBorrowerName() { return borrowerName; }
    public BigDecimal getOriginalPrincipal() { return originalPrincipal; }
    public BigDecimal getRemainingPrincipal() { return remainingPrincipal; }
    public BigDecimal getAnnualRatePct() { return annualRatePct; }
    public int getTermMonths() { return termMonths; }
    public LocalDate getStartDate() { return startDate; }
    public BigDecimal getEscrowMonthly() { return escrowMonthly; }
    public BigDecimal getEscrowBalance() { return escrowBalance; }
    public BigDecimal getMonthlyPayment() { return monthlyPayment; }
    public LocalDate getLastPaymentDate() { return lastPaymentDate; }
    public LoanStatus getStatus() { return status; }
}
