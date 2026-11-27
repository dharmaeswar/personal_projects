package com.dharma.mortgage.service;

import com.dharma.mortgage.dto.AmortizationEntryResponse;
import com.dharma.mortgage.dto.CreateLoanRequest;
import com.dharma.mortgage.dto.LoanResponse;
import com.dharma.mortgage.dto.PaymentRequest;
import com.dharma.mortgage.dto.PaymentResponse;
import com.dharma.mortgage.model.Amortization;
import com.dharma.mortgage.model.AmortizationEntry;
import com.dharma.mortgage.model.Loan;
import com.dharma.mortgage.model.Payment;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Loan servicing rules, enforced here and not in the controller:
 * <ul>
 *   <li>Money is BigDecimal (scale 2); doubles are never used for money.</li>
 *   <li>A payment must at least cover this month's interest plus escrow. Anything
 *       above that split goes to principal; a payment that would overpay the loan
 *       is capped at the remaining balance.</li>
 *   <li>A repeated idempotency key replays the original payment instead of
 *       applying the money twice.</li>
 *   <li>Payments on one loan are serialized on the loan lock, so concurrent
 *       payments cannot corrupt the remaining balance.</li>
 * </ul>
 * Logging never includes borrower names, balances, or full loan ids.
 */
@Service
public class LoanService {
    private static final Logger log = LoggerFactory.getLogger(LoanService.class);
    private final com.dharma.mortgage.repository.LoanRepository repository;
    /** idempotencyKey -> resulting payment response, kept in memory for this demo. */
    private final Map<String, PaymentResponse> paymentResults = new ConcurrentHashMap<>();

    public LoanService(com.dharma.mortgage.repository.LoanRepository repository) {
        this.repository = repository;
    }

    public LoanResponse createLoan(CreateLoanRequest request) {
        Loan loan = new Loan(request.getBorrowerName(), request.getOriginalPrincipal(),
                request.getAnnualRatePct(), request.getTermMonths(), request.getStartDate(),
                request.getEscrowMonthly());
        repository.save(loan);
        log.info("Loan created termMonths={}", request.getTermMonths());
        return new LoanResponse(loan);
    }

    public LoanResponse getLoan(String id) {
        return new LoanResponse(requireLoan(id));
    }

    public List<LoanResponse> listLoans() {
        return repository.findAll().stream().map(LoanResponse::new).toList();
    }

    public PaymentResponse applyPayment(String loanId, PaymentRequest request) {
        if (request.getIdempotencyKey() != null
                && paymentResults.containsKey(request.getIdempotencyKey())) {
            log.info("Duplicate payment replayed from idempotency key");
            return paymentResults.get(request.getIdempotencyKey());
        }
        Loan loan = requireLoan(loanId);
        Payment payment;
        synchronized (loan) {
            if (loan.getStatus() == com.dharma.mortgage.model.LoanStatus.PAID_OFF) {
                throw new IllegalArgumentException("Loan is already paid off");
            }
            BigDecimal minimumDue = loan.monthlyInterest().add(loan.getEscrowMonthly());
            if (request.getAmount().compareTo(minimumDue) < 0) {
                throw new InvalidPaymentException(request.getAmount(), minimumDue);
            }
            payment = loan.applyPayment(request.getAmount(), request.getPaymentDate(),
                    request.getIdempotencyKey());
        }
        PaymentResponse result = new PaymentResponse(payment);
        if (request.getIdempotencyKey() != null) {
            paymentResults.put(request.getIdempotencyKey(), result);
        }
        log.info("Payment applied");
        return result;
    }

    public List<PaymentResponse> paymentHistory(String loanId) {
        return requireLoan(loanId).getPayments().stream()
                .map(PaymentResponse::new).toList();
    }

    public List<AmortizationEntryResponse> amortizationSchedule(String loanId) {
        Loan loan = requireLoan(loanId);
        int monthsPaid = loan.getPayments().size();
        int monthsLeft = Math.max(loan.getTermMonths() - monthsPaid, 0);
        List<AmortizationEntry> entries = Amortization.schedule(
                loan.getRemainingPrincipal(), loan.getAnnualRatePct(),
                loan.monthlyPayment(), loan.getEscrowMonthly(), monthsLeft, monthsPaid + 1);
        return entries.stream().map(AmortizationEntryResponse::new).toList();
    }

    /** Escrow snapshot: monthly amount, balance held, and the next annual analysis date. */
    public EscrowSummary escrow(String loanId) {
        Loan loan = requireLoan(loanId);
        LocalDate nextAnalysis = loan.getStartDate().plusYears(1);
        while (!nextAnalysis.isAfter(LocalDate.now())) {
            nextAnalysis = nextAnalysis.plusYears(1);
        }
        return new EscrowSummary(loan.getEscrowMonthly(), loan.getEscrowBalance(), nextAnalysis);
    }

    /** True when the loan has had no payment within 30 days of the given date. */
    public boolean isDelinquent(String loanId, LocalDate asOf) {
        Loan loan = requireLoan(loanId);
        boolean delinquent = loan.isDelinquent(asOf);
        if (delinquent) {
            synchronized (loan) {
                loan.markDelinquent();
            }
        }
        return delinquent;
    }

    private Loan requireLoan(String id) {
        return repository.findById(id).orElseThrow(() -> new LoanNotFoundException(id));
    }

    public record EscrowSummary(BigDecimal escrowMonthly, BigDecimal escrowBalance,
                                LocalDate nextAnalysisDate) {}
}
