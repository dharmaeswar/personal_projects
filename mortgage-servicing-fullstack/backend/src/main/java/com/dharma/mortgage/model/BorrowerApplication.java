package com.dharma.mortgage.model;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * A borrower home-lending application moving through intake, decisioning and
 * closing. Money is always BigDecimal (scale 2); ratios are scale 4.
 * State only moves inside {@link com.dharma.mortgage.service.ApplicationService},
 * so an application can never skip a stage or be funded before closing is done.
 * No real borrower data is involved: every field here is demo input.
 */
public class BorrowerApplication {
    /** Closing checklist: every item must be complete before funding. */
    public static final List<String> CLOSING_ITEMS = List.of(
            "APPRAISAL", "TITLE_SEARCH", "HOMEOWNERS_INSURANCE", "FINAL_DISCLOSURE");

    private final String id;
    private final String borrowerName;
    private final BigDecimal requestedAmount;
    private final BigDecimal homeValue;
    private final BigDecimal annualIncome;
    private final BigDecimal monthlyDebts;
    private final int creditScore;
    private ApplicationStatus status;
    private DecisionOutcome decision;
    private final List<String> decisionReasons = new ArrayList<>();
    private final Map<String, Boolean> closingChecklist = new LinkedHashMap<>();
    private LocalDateTime submittedAt;
    private LocalDateTime decidedAt;
    private LocalDateTime fundedAt;

    public BorrowerApplication(String borrowerName, BigDecimal requestedAmount,
            BigDecimal homeValue, BigDecimal annualIncome, BigDecimal monthlyDebts,
            int creditScore) {
        this.id = UUID.randomUUID().toString();
        this.borrowerName = borrowerName;
        this.requestedAmount = requestedAmount.setScale(2, RoundingMode.HALF_UP);
        this.homeValue = homeValue.setScale(2, RoundingMode.HALF_UP);
        this.annualIncome = annualIncome.setScale(2, RoundingMode.HALF_UP);
        this.monthlyDebts = monthlyDebts.setScale(2, RoundingMode.HALF_UP);
        this.creditScore = creditScore;
        this.status = ApplicationStatus.STARTED;
        for (String item : CLOSING_ITEMS) {
            closingChecklist.put(item, false);
        }
    }

    public String getId() { return id; }
    public String getBorrowerName() { return borrowerName; }
    public BigDecimal getRequestedAmount() { return requestedAmount; }
    public BigDecimal getHomeValue() { return homeValue; }
    public BigDecimal getAnnualIncome() { return annualIncome; }
    public BigDecimal getMonthlyDebts() { return monthlyDebts; }
    public int getCreditScore() { return creditScore; }
    public synchronized ApplicationStatus getStatus() { return status; }
    public synchronized DecisionOutcome getDecision() { return decision; }
    public synchronized List<String> getDecisionReasons() {
        return Collections.unmodifiableList(new ArrayList<>(decisionReasons));
    }
    public synchronized Map<String, Boolean> getClosingChecklist() {
        return Collections.unmodifiableMap(new LinkedHashMap<>(closingChecklist));
    }
    public synchronized LocalDateTime getSubmittedAt() { return submittedAt; }
    public synchronized LocalDateTime getDecidedAt() { return decidedAt; }
    public synchronized LocalDateTime getFundedAt() { return fundedAt; }

    /** Loan-to-value: requested amount divided by home value. */
    public BigDecimal loanToValue() {
        return requestedAmount.divide(homeValue, 4, RoundingMode.HALF_UP);
    }

    /** Debt-to-income: monthly debts divided by gross monthly income. */
    public BigDecimal debtToIncome() {
        BigDecimal monthlyIncome = annualIncome.divide(BigDecimal.valueOf(12), 4, RoundingMode.HALF_UP);
        return monthlyDebts.divide(monthlyIncome, 4, RoundingMode.HALF_UP);
    }

    public synchronized void submit() {
        status = ApplicationStatus.SUBMITTED;
        submittedAt = LocalDateTime.now();
    }

    public synchronized void applyDecision(DecisionOutcome outcome, List<String> reasons) {
        decision = outcome;
        decisionReasons.clear();
        decisionReasons.addAll(reasons);
        decidedAt = LocalDateTime.now();
        status = switch (outcome) {
            case APPROVED -> ApplicationStatus.APPROVED;
            case CONDITIONAL -> ApplicationStatus.CONDITIONAL;
            case DENIED -> ApplicationStatus.DENIED;
        };
    }

    public synchronized void startClosing() {
        status = ApplicationStatus.CLOSING;
    }

    public synchronized boolean completeClosingItem(String item) {
        if (!closingChecklist.containsKey(item)) {
            return false;
        }
        closingChecklist.put(item, true);
        return true;
    }

    public synchronized boolean closingComplete() {
        return closingChecklist.values().stream().allMatch(Boolean::booleanValue);
    }

    public synchronized void fund() {
        status = ApplicationStatus.FUNDED;
        fundedAt = LocalDateTime.now();
    }
}
