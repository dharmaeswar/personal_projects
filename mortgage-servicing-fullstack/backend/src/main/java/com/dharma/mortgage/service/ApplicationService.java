package com.dharma.mortgage.service;

import com.dharma.mortgage.dto.ApplicationResponse;
import com.dharma.mortgage.dto.CreateApplicationRequest;
import com.dharma.mortgage.dto.FunnelMetricsResponse;
import com.dharma.mortgage.model.ApplicationStatus;
import com.dharma.mortgage.model.BorrowerApplication;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Borrower application lifecycle, enforced here and not in the controller:
 * <ul>
 *   <li>STARTED &rarr; SUBMITTED &rarr; APPROVED / CONDITIONAL / DENIED.</li>
 *   <li>APPROVED or CONDITIONAL &rarr; CLOSING &rarr; FUNDED, only once every
 *       closing-checklist item is complete.</li>
 *   <li>An out-of-order transition is rejected, never silently applied.</li>
 *   <li>Funnel metrics count applications per stage and the conversion
 *       between stages, so drop-off is visible.</li>
 * </ul>
 * Logging never includes borrower names or amounts.
 */
@Service
public class ApplicationService {
    private static final Logger log = LoggerFactory.getLogger(ApplicationService.class);
    private final DecisioningService decisioning;
    private final ConcurrentMap<String, BorrowerApplication> store = new ConcurrentHashMap<>();

    public ApplicationService(DecisioningService decisioning) {
        this.decisioning = decisioning;
    }

    public ApplicationResponse createApplication(CreateApplicationRequest request) {
        BorrowerApplication application = new BorrowerApplication(
                request.getBorrowerName(), request.getRequestedAmount(), request.getHomeValue(),
                request.getAnnualIncome(), request.getMonthlyDebts(), request.getCreditScore());
        store.put(application.getId(), application);
        log.info("Application created status={}", application.getStatus());
        return new ApplicationResponse(application);
    }

    public ApplicationResponse getApplication(String id) {
        return new ApplicationResponse(requireApplication(id));
    }

    public List<ApplicationResponse> listApplications() {
        return store.values().stream().map(ApplicationResponse::new).toList();
    }

    public ApplicationResponse submitApplication(String id) {
        BorrowerApplication application = requireApplication(id);
        if (application.getStatus() != ApplicationStatus.STARTED) {
            throw new InvalidApplicationStateException(id, application.getStatus(), "SUBMITTED");
        }
        application.submit();
        log.info("Application submitted");
        return new ApplicationResponse(application);
    }

    public ApplicationResponse decideApplication(String id) {
        BorrowerApplication application = requireApplication(id);
        if (application.getStatus() != ApplicationStatus.SUBMITTED) {
            throw new InvalidApplicationStateException(id, application.getStatus(), "DECIDED");
        }
        DecisioningService.Decision decision = decisioning.decide(application);
        application.applyDecision(decision.outcome(), decision.reasons());
        log.info("Application decided outcome={}", decision.outcome());
        return new ApplicationResponse(application);
    }

    public ApplicationResponse startClosing(String id) {
        BorrowerApplication application = requireApplication(id);
        if (application.getStatus() != ApplicationStatus.APPROVED
                && application.getStatus() != ApplicationStatus.CONDITIONAL) {
            throw new InvalidApplicationStateException(id, application.getStatus(), "CLOSING");
        }
        application.startClosing();
        log.info("Application moved to closing");
        return new ApplicationResponse(application);
    }

    public ApplicationResponse completeClosingItem(String id, String item) {
        BorrowerApplication application = requireApplication(id);
        if (application.getStatus() != ApplicationStatus.CLOSING) {
            throw new InvalidApplicationStateException(id, application.getStatus(),
                    "CLOSING item " + item);
        }
        if (!application.completeClosingItem(item)) {
            throw new IllegalArgumentException("Unknown closing item: " + item);
        }
        return new ApplicationResponse(application);
    }

    public ApplicationResponse fundApplication(String id) {
        BorrowerApplication application = requireApplication(id);
        if (application.getStatus() != ApplicationStatus.CLOSING) {
            throw new InvalidApplicationStateException(id, application.getStatus(), "FUNDED");
        }
        if (!application.closingComplete()) {
            throw new InvalidApplicationStateException(id, application.getStatus(),
                    "FUNDED with an incomplete closing checklist");
        }
        application.fund();
        log.info("Application funded");
        return new ApplicationResponse(application);
    }

    public FunnelMetricsResponse funnelMetrics() {
        Map<ApplicationStatus, Long> counts = new EnumMap<>(ApplicationStatus.class);
        for (ApplicationStatus status : ApplicationStatus.values()) {
            counts.put(status, 0L);
        }
        for (BorrowerApplication application : store.values()) {
            counts.merge(application.getStatus(), 1L, Long::sum);
        }
        long total = store.size();
        long started = counts.get(ApplicationStatus.STARTED);
        long submitted = counts.get(ApplicationStatus.SUBMITTED)
                + counts.get(ApplicationStatus.APPROVED)
                + counts.get(ApplicationStatus.CONDITIONAL)
                + counts.get(ApplicationStatus.DENIED)
                + counts.get(ApplicationStatus.CLOSING)
                + counts.get(ApplicationStatus.FUNDED);
        long decided = counts.get(ApplicationStatus.APPROVED)
                + counts.get(ApplicationStatus.CONDITIONAL)
                + counts.get(ApplicationStatus.DENIED)
                + counts.get(ApplicationStatus.CLOSING)
                + counts.get(ApplicationStatus.FUNDED);
        long approvedOrConditional = counts.get(ApplicationStatus.APPROVED)
                + counts.get(ApplicationStatus.CONDITIONAL)
                + counts.get(ApplicationStatus.CLOSING)
                + counts.get(ApplicationStatus.FUNDED);
        long funded = counts.get(ApplicationStatus.FUNDED);
        return new FunnelMetricsResponse(total, started, submitted, decided,
                approvedOrConditional, funded, counts,
                rate(submitted, total), rate(decided, submitted),
                rate(approvedOrConditional, decided), rate(funded, approvedOrConditional));
    }

    private static double rate(long part, long whole) {
        if (whole == 0) {
            return 0.0;
        }
        return Math.round(1000.0 * part / whole) / 10.0;
    }

    private BorrowerApplication requireApplication(String id) {
        BorrowerApplication application = store.get(id);
        if (application == null) {
            throw new ApplicationNotFoundException(id);
        }
        return application;
    }
}
