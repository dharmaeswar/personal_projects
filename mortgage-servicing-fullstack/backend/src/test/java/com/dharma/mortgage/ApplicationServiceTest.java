package com.dharma.mortgage;

import com.dharma.mortgage.dto.ApplicationResponse;
import com.dharma.mortgage.dto.CreateApplicationRequest;
import com.dharma.mortgage.dto.FunnelMetricsResponse;
import com.dharma.mortgage.model.ApplicationStatus;
import com.dharma.mortgage.model.BorrowerApplication;
import com.dharma.mortgage.service.ApplicationNotFoundException;
import com.dharma.mortgage.service.ApplicationService;
import com.dharma.mortgage.service.DecisioningService;
import com.dharma.mortgage.service.InvalidApplicationStateException;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ApplicationServiceTest {
    private final ApplicationService service = new ApplicationService(new DecisioningService());

    private CreateApplicationRequest request(int creditScore, String amount,
            String homeValue, String annualIncome, String monthlyDebts) {
        CreateApplicationRequest request = new CreateApplicationRequest();
        request.setBorrowerName("Test Borrower");
        request.setRequestedAmount(new BigDecimal(amount));
        request.setHomeValue(new BigDecimal(homeValue));
        request.setAnnualIncome(new BigDecimal(annualIncome));
        request.setMonthlyDebts(new BigDecimal(monthlyDebts));
        request.setCreditScore(creditScore);
        return request;
    }

    private ApplicationResponse strongApplication() {
        return service.createApplication(request(720, "300000", "400000", "120000", "3000"));
    }

    private ApplicationResponse fundReadyApplication() {
        ApplicationResponse application = strongApplication();
        application = service.submitApplication(application.getId());
        application = service.decideApplication(application.getId());
        application = service.startClosing(application.getId());
        for (String item : BorrowerApplication.CLOSING_ITEMS) {
            application = service.completeClosingItem(application.getId(), item);
        }
        return application;
    }

    @Test
    void fullLifecycleFromStartToFunded() {
        ApplicationResponse application = strongApplication();
        assertEquals(ApplicationStatus.STARTED, application.getStatus());

        application = service.submitApplication(application.getId());
        assertEquals(ApplicationStatus.SUBMITTED, application.getStatus());

        application = service.decideApplication(application.getId());
        assertEquals(ApplicationStatus.APPROVED, application.getStatus());
        assertTrue(application.getDecisionReasons().size() >= 1);

        application = service.startClosing(application.getId());
        assertEquals(ApplicationStatus.CLOSING, application.getStatus());
        assertFalse(application.getClosingChecklist().values().stream().allMatch(b -> b));

        application = service.completeClosingItem(application.getId(), "APPRAISAL");
        assertTrue(application.getClosingChecklist().get("APPRAISAL"));

        // Funding is still blocked: three checklist items remain open.
        String id = application.getId();
        assertThrows(InvalidApplicationStateException.class, () -> service.fundApplication(id));
        assertEquals(ApplicationStatus.CLOSING, service.getApplication(id).getStatus());
    }

    @Test
    void fundingSucceedsOnceChecklistIsComplete() {
        ApplicationResponse application = fundReadyApplication();
        application = service.fundApplication(application.getId());
        assertEquals(ApplicationStatus.FUNDED, application.getStatus());
        assertTrue(application.getFundedAt() != null);
    }

    @Test
    void deniedApplicationCannotMoveToClosing() {
        ApplicationResponse application =
                service.createApplication(request(600, "300000", "400000", "120000", "3000"));
        application = service.submitApplication(application.getId());
        application = service.decideApplication(application.getId());
        assertEquals(ApplicationStatus.DENIED, application.getStatus());
        String id = application.getId();
        assertThrows(InvalidApplicationStateException.class, () -> service.startClosing(id));
    }

    @Test
    void decideBeforeSubmitIsRejected() {
        ApplicationResponse application = strongApplication();
        String id = application.getId();
        assertThrows(InvalidApplicationStateException.class, () -> service.decideApplication(id));
    }

    @Test
    void fundingBeforeClosingIsRejected() {
        ApplicationResponse application = strongApplication();
        application = service.submitApplication(application.getId());
        application = service.decideApplication(application.getId());
        String id = application.getId();
        assertThrows(InvalidApplicationStateException.class, () -> service.fundApplication(id));
    }

    @Test
    void unknownClosingItemIsRejected() {
        ApplicationResponse application = strongApplication();
        application = service.submitApplication(application.getId());
        application = service.decideApplication(application.getId());
        application = service.startClosing(application.getId());
        String id = application.getId();
        assertThrows(IllegalArgumentException.class,
                () -> service.completeClosingItem(id, "NOT_A_REAL_ITEM"));
    }

    @Test
    void unknownApplicationIsNotFound() {
        assertThrows(ApplicationNotFoundException.class,
                () -> service.getApplication("no-such-id"));
    }

    @Test
    void funnelMetricsCountStagesAndConversions() {
        // One funded, one denied, one still started: 3 total.
        ApplicationResponse ready = fundReadyApplication();
        service.fundApplication(ready.getId());
        ApplicationResponse denied =
                service.createApplication(request(600, "300000", "400000", "120000", "3000"));
        service.submitApplication(denied.getId());
        service.decideApplication(denied.getId());
        strongApplication();

        FunnelMetricsResponse funnel = service.funnelMetrics();
        assertEquals(3, funnel.getTotal());
        assertEquals(1, funnel.getStarted());
        assertEquals(2, funnel.getSubmitted());
        assertEquals(2, funnel.getDecided());
        assertEquals(1, funnel.getApprovedOrConditional());
        assertEquals(1, funnel.getFunded());
        assertEquals(66.7, funnel.getSubmissionRatePct(), 0.01);
        assertEquals(100.0, funnel.getDecisionRatePct(), 0.01);
        assertEquals(50.0, funnel.getApprovalRatePct(), 0.01);
        assertEquals(100.0, funnel.getFundingRatePct(), 0.01);
        assertEquals(1L, funnel.getCountsByStatus().get(ApplicationStatus.FUNDED).longValue());
    }

    @Test
    void emptyFunnelRatesAreZeroNotNaN() {
        FunnelMetricsResponse funnel = service.funnelMetrics();
        assertEquals(0, funnel.getTotal());
        assertEquals(0.0, funnel.getSubmissionRatePct(), 0.01);
        assertEquals(0.0, funnel.getFundingRatePct(), 0.01);
        List<ApplicationResponse> all = service.listApplications();
        assertTrue(all.isEmpty());
    }
}
