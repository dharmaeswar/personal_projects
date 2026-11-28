package com.dharma.mortgage.service;

import com.dharma.mortgage.model.BorrowerApplication;
import com.dharma.mortgage.model.DecisionOutcome;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;

/**
 * Deterministic lending decisioning rules, kept pure so every outcome is
 * reproducible from the application alone. These are demo underwriting
 * thresholds, not a real lender's policy:
 * <ul>
 *   <li>DENY when credit score &lt; 620, loan-to-value &gt; 0.90, or
 *       debt-to-income &gt; 0.50.</li>
 *   <li>CONDITIONAL when credit score &lt; 680, loan-to-value &gt; 0.80, or
 *       debt-to-income &gt; 0.43 — the file needs conditions before closing.</li>
 *   <li>APPROVE otherwise.</li>
 * </ul>
 * Every rule that fires is reported as a reason, so a denied or conditional
 * application always explains itself.
 */
@Service
public class DecisioningService {
    private static final BigDecimal DENY_CREDIT_SCORE = BigDecimal.valueOf(620);
    private static final BigDecimal DENY_LTV = new BigDecimal("0.90");
    private static final BigDecimal DENY_DTI = new BigDecimal("0.50");
    private static final BigDecimal CONDITIONAL_CREDIT_SCORE = BigDecimal.valueOf(680);
    private static final BigDecimal CONDITIONAL_LTV = new BigDecimal("0.80");
    private static final BigDecimal CONDITIONAL_DTI = new BigDecimal("0.43");

    public record Decision(DecisionOutcome outcome, List<String> reasons) {}

    public Decision decide(BorrowerApplication application) {
        List<String> denyReasons = new ArrayList<>();
        List<String> conditionalReasons = new ArrayList<>();
        BigDecimal ltv = application.loanToValue();
        BigDecimal dti = application.debtToIncome();

        if (BigDecimal.valueOf(application.getCreditScore()).compareTo(DENY_CREDIT_SCORE) < 0) {
            denyReasons.add("Credit score " + application.getCreditScore() + " is below 620");
        }
        if (ltv.compareTo(DENY_LTV) > 0) {
            denyReasons.add("Loan-to-value " + ltv + " is above 0.90");
        }
        if (dti.compareTo(DENY_DTI) > 0) {
            denyReasons.add("Debt-to-income " + dti + " is above 0.50");
        }
        if (!denyReasons.isEmpty()) {
            return new Decision(DecisionOutcome.DENIED, denyReasons);
        }

        if (BigDecimal.valueOf(application.getCreditScore()).compareTo(CONDITIONAL_CREDIT_SCORE) < 0) {
            conditionalReasons.add("Credit score " + application.getCreditScore() + " is below 680");
        }
        if (ltv.compareTo(CONDITIONAL_LTV) > 0) {
            conditionalReasons.add("Loan-to-value " + ltv + " is above 0.80");
        }
        if (dti.compareTo(CONDITIONAL_DTI) > 0) {
            conditionalReasons.add("Debt-to-income " + dti + " is above 0.43");
        }
        if (!conditionalReasons.isEmpty()) {
            return new Decision(DecisionOutcome.CONDITIONAL, conditionalReasons);
        }
        return new Decision(DecisionOutcome.APPROVED,
                List.of("Credit score, loan-to-value and debt-to-income all meet approval thresholds"));
    }
}
