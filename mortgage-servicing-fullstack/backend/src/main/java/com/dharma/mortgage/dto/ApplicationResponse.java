package com.dharma.mortgage.dto;

import com.dharma.mortgage.model.ApplicationStatus;
import com.dharma.mortgage.model.BorrowerApplication;
import com.dharma.mortgage.model.DecisionOutcome;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

public class ApplicationResponse {
    private final String id;
    private final String borrowerName;
    private final BigDecimal requestedAmount;
    private final BigDecimal homeValue;
    private final BigDecimal annualIncome;
    private final BigDecimal monthlyDebts;
    private final int creditScore;
    private final BigDecimal loanToValue;
    private final BigDecimal debtToIncome;
    private final ApplicationStatus status;
    private final DecisionOutcome decision;
    private final List<String> decisionReasons;
    private final Map<String, Boolean> closingChecklist;
    private final LocalDateTime submittedAt;
    private final LocalDateTime decidedAt;
    private final LocalDateTime fundedAt;

    public ApplicationResponse(BorrowerApplication application) {
        this.id = application.getId();
        this.borrowerName = application.getBorrowerName();
        this.requestedAmount = application.getRequestedAmount();
        this.homeValue = application.getHomeValue();
        this.annualIncome = application.getAnnualIncome();
        this.monthlyDebts = application.getMonthlyDebts();
        this.creditScore = application.getCreditScore();
        this.loanToValue = application.loanToValue();
        this.debtToIncome = application.debtToIncome();
        this.status = application.getStatus();
        this.decision = application.getDecision();
        this.decisionReasons = application.getDecisionReasons();
        this.closingChecklist = application.getClosingChecklist();
        this.submittedAt = application.getSubmittedAt();
        this.decidedAt = application.getDecidedAt();
        this.fundedAt = application.getFundedAt();
    }

    public String getId() { return id; }
    public String getBorrowerName() { return borrowerName; }
    public BigDecimal getRequestedAmount() { return requestedAmount; }
    public BigDecimal getHomeValue() { return homeValue; }
    public BigDecimal getAnnualIncome() { return annualIncome; }
    public BigDecimal getMonthlyDebts() { return monthlyDebts; }
    public int getCreditScore() { return creditScore; }
    public BigDecimal getLoanToValue() { return loanToValue; }
    public BigDecimal getDebtToIncome() { return debtToIncome; }
    public ApplicationStatus getStatus() { return status; }
    public DecisionOutcome getDecision() { return decision; }
    public List<String> getDecisionReasons() { return decisionReasons; }
    public Map<String, Boolean> getClosingChecklist() { return closingChecklist; }
    public LocalDateTime getSubmittedAt() { return submittedAt; }
    public LocalDateTime getDecidedAt() { return decidedAt; }
    public LocalDateTime getFundedAt() { return fundedAt; }
}
