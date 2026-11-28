package com.dharma.mortgage;

import com.dharma.mortgage.model.BorrowerApplication;
import com.dharma.mortgage.model.DecisionOutcome;
import com.dharma.mortgage.service.DecisioningService;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DecisioningServiceTest {
    private final DecisioningService decisioning = new DecisioningService();

    private BorrowerApplication application(int creditScore, String amount,
            String homeValue, String annualIncome, String monthlyDebts) {
        return new BorrowerApplication("Test Borrower", new BigDecimal(amount),
                new BigDecimal(homeValue), new BigDecimal(annualIncome),
                new BigDecimal(monthlyDebts), creditScore);
    }

    @Test
    void strongFileApproves() {
        // LTV 0.75, DTI 0.30, score 720: every threshold met.
        DecisioningService.Decision decision =
                decisioning.decide(application(720, "300000", "400000", "120000", "3000"));
        assertEquals(DecisionOutcome.APPROVED, decision.outcome());
        assertEquals(1, decision.reasons().size());
    }

    @Test
    void exactApprovalBoundariesApprove() {
        // Score 680, LTV exactly 0.80, DTI exactly 0.43: thresholds are inclusive.
        DecisioningService.Decision decision =
                decisioning.decide(application(680, "320000", "400000", "120000", "4300"));
        assertEquals(DecisionOutcome.APPROVED, decision.outcome());
    }

    @Test
    void lowCreditScoreIsConditional() {
        // Score 679 with clean LTV and DTI: conditional, with the score named.
        DecisioningService.Decision decision =
                decisioning.decide(application(679, "300000", "400000", "120000", "3000"));
        assertEquals(DecisionOutcome.CONDITIONAL, decision.outcome());
        assertTrue(decision.reasons().stream().anyMatch(r -> r.contains("679")));
    }

    @Test
    void highLtvIsConditional() {
        // LTV 0.85, score and DTI clean: conditional on the LTV rule.
        DecisioningService.Decision decision =
                decisioning.decide(application(720, "340000", "400000", "120000", "3000"));
        assertEquals(DecisionOutcome.CONDITIONAL, decision.outcome());
        assertTrue(decision.reasons().stream().anyMatch(r -> r.contains("Loan-to-value")));
    }

    @Test
    void highDtiIsConditional() {
        // DTI 0.45, score and LTV clean: conditional on the DTI rule.
        DecisioningService.Decision decision =
                decisioning.decide(application(720, "300000", "400000", "120000", "4500"));
        assertEquals(DecisionOutcome.CONDITIONAL, decision.outcome());
        assertTrue(decision.reasons().stream().anyMatch(r -> r.contains("Debt-to-income")));
    }

    @Test
    void scoreBelow620Denies() {
        DecisioningService.Decision decision =
                decisioning.decide(application(619, "300000", "400000", "120000", "3000"));
        assertEquals(DecisionOutcome.DENIED, decision.outcome());
        assertTrue(decision.reasons().stream().anyMatch(r -> r.contains("619")));
    }

    @Test
    void ltvAboveNinetyDenies() {
        // LTV 0.95: denied even with a strong score and low DTI.
        DecisioningService.Decision decision =
                decisioning.decide(application(760, "380000", "400000", "120000", "3000"));
        assertEquals(DecisionOutcome.DENIED, decision.outcome());
        assertTrue(decision.reasons().stream().anyMatch(r -> r.contains("Loan-to-value")));
    }

    @Test
    void dtiAboveFiftyDenies() {
        // DTI 0.60: denied even with a strong score and low LTV.
        DecisioningService.Decision decision =
                decisioning.decide(application(760, "300000", "400000", "120000", "6000"));
        assertEquals(DecisionOutcome.DENIED, decision.outcome());
        assertTrue(decision.reasons().stream().anyMatch(r -> r.contains("Debt-to-income")));
    }

    @Test
    void multipleDenyReasonsAreAllReported() {
        // Score 600 and LTV 0.95: both deny reasons come back.
        DecisioningService.Decision decision =
                decisioning.decide(application(600, "380000", "400000", "120000", "3000"));
        assertEquals(DecisionOutcome.DENIED, decision.outcome());
        assertEquals(2, decision.reasons().size());
    }

    @Test
    void ltvAndDtiAreComputedCorrectly() {
        BorrowerApplication application =
                application(720, "300000", "400000", "120000", "3000");
        assertEquals(new BigDecimal("0.7500"), application.loanToValue());
        assertEquals(new BigDecimal("0.3000"), application.debtToIncome());
    }
}
