package com.dharma.mortgage.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.LocalDate;

public class CreateLoanRequest {
    @NotBlank(message = "borrowerName is required")
    private String borrowerName;

    @NotNull(message = "originalPrincipal is required")
    @DecimalMin(value = "1000.00", message = "originalPrincipal must be at least 1000.00")
    private BigDecimal originalPrincipal;

    @NotNull(message = "annualRatePct is required")
    @DecimalMin(value = "0.00", message = "annualRatePct must be at least 0.00")
    private BigDecimal annualRatePct;

    @Min(value = 12, message = "termMonths must be at least 12")
    private int termMonths;

    @NotNull(message = "startDate is required")
    private LocalDate startDate;

    @NotNull(message = "escrowMonthly is required")
    @DecimalMin(value = "0.00", message = "escrowMonthly must be at least 0.00")
    private BigDecimal escrowMonthly;

    public String getBorrowerName() { return borrowerName; }
    public void setBorrowerName(String borrowerName) { this.borrowerName = borrowerName; }
    public BigDecimal getOriginalPrincipal() { return originalPrincipal; }
    public void setOriginalPrincipal(BigDecimal originalPrincipal) { this.originalPrincipal = originalPrincipal; }
    public BigDecimal getAnnualRatePct() { return annualRatePct; }
    public void setAnnualRatePct(BigDecimal annualRatePct) { this.annualRatePct = annualRatePct; }
    public int getTermMonths() { return termMonths; }
    public void setTermMonths(int termMonths) { this.termMonths = termMonths; }
    public LocalDate getStartDate() { return startDate; }
    public void setStartDate(LocalDate startDate) { this.startDate = startDate; }
    public BigDecimal getEscrowMonthly() { return escrowMonthly; }
    public void setEscrowMonthly(BigDecimal escrowMonthly) { this.escrowMonthly = escrowMonthly; }
}
