package com.dharma.mortgage.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;

public class CreateApplicationRequest {
    @NotBlank(message = "borrowerName is required")
    private String borrowerName;

    @NotNull(message = "requestedAmount is required")
    @DecimalMin(value = "1000.00", message = "requestedAmount must be at least 1000.00")
    private BigDecimal requestedAmount;

    @NotNull(message = "homeValue is required")
    @DecimalMin(value = "1000.00", message = "homeValue must be at least 1000.00")
    private BigDecimal homeValue;

    @NotNull(message = "annualIncome is required")
    @DecimalMin(value = "0.01", message = "annualIncome must be greater than 0")
    private BigDecimal annualIncome;

    @NotNull(message = "monthlyDebts is required")
    @DecimalMin(value = "0.00", message = "monthlyDebts must be at least 0.00")
    private BigDecimal monthlyDebts;

    @Min(value = 300, message = "creditScore must be at least 300")
    @Max(value = 850, message = "creditScore must be at most 850")
    private int creditScore;

    public String getBorrowerName() { return borrowerName; }
    public void setBorrowerName(String borrowerName) { this.borrowerName = borrowerName; }
    public BigDecimal getRequestedAmount() { return requestedAmount; }
    public void setRequestedAmount(BigDecimal requestedAmount) { this.requestedAmount = requestedAmount; }
    public BigDecimal getHomeValue() { return homeValue; }
    public void setHomeValue(BigDecimal homeValue) { this.homeValue = homeValue; }
    public BigDecimal getAnnualIncome() { return annualIncome; }
    public void setAnnualIncome(BigDecimal annualIncome) { this.annualIncome = annualIncome; }
    public BigDecimal getMonthlyDebts() { return monthlyDebts; }
    public void setMonthlyDebts(BigDecimal monthlyDebts) { this.monthlyDebts = monthlyDebts; }
    public int getCreditScore() { return creditScore; }
    public void setCreditScore(int creditScore) { this.creditScore = creditScore; }
}
