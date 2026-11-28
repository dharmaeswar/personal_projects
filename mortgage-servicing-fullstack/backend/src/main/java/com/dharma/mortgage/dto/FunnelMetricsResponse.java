package com.dharma.mortgage.dto;

import com.dharma.mortgage.model.ApplicationStatus;
import java.util.Map;

/** Funnel counts per stage plus the conversion rate between each pair of stages. */
public class FunnelMetricsResponse {
    private final long total;
    private final long started;
    private final long submitted;
    private final long decided;
    private final long approvedOrConditional;
    private final long funded;
    private final Map<ApplicationStatus, Long> countsByStatus;
    private final double submissionRatePct;
    private final double decisionRatePct;
    private final double approvalRatePct;
    private final double fundingRatePct;

    public FunnelMetricsResponse(long total, long started, long submitted, long decided,
            long approvedOrConditional, long funded, Map<ApplicationStatus, Long> countsByStatus,
            double submissionRatePct, double decisionRatePct,
            double approvalRatePct, double fundingRatePct) {
        this.total = total;
        this.started = started;
        this.submitted = submitted;
        this.decided = decided;
        this.approvedOrConditional = approvedOrConditional;
        this.funded = funded;
        this.countsByStatus = countsByStatus;
        this.submissionRatePct = submissionRatePct;
        this.decisionRatePct = decisionRatePct;
        this.approvalRatePct = approvalRatePct;
        this.fundingRatePct = fundingRatePct;
    }

    public long getTotal() { return total; }
    public long getStarted() { return started; }
    public long getSubmitted() { return submitted; }
    public long getDecided() { return decided; }
    public long getApprovedOrConditional() { return approvedOrConditional; }
    public long getFunded() { return funded; }
    public Map<ApplicationStatus, Long> getCountsByStatus() { return countsByStatus; }
    public double getSubmissionRatePct() { return submissionRatePct; }
    public double getDecisionRatePct() { return decisionRatePct; }
    public double getApprovalRatePct() { return approvalRatePct; }
    public double getFundingRatePct() { return fundingRatePct; }
}
