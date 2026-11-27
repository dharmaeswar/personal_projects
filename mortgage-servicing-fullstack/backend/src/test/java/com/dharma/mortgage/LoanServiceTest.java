package com.dharma.mortgage;

import com.dharma.mortgage.dto.CreateLoanRequest;
import com.dharma.mortgage.dto.LoanResponse;
import com.dharma.mortgage.dto.PaymentRequest;
import com.dharma.mortgage.dto.PaymentResponse;
import com.dharma.mortgage.model.Amortization;
import com.dharma.mortgage.repository.InMemoryLoanRepository;
import com.dharma.mortgage.service.InvalidPaymentException;
import com.dharma.mortgage.service.LoanService;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LoanServiceTest {
    private final LoanService service = new LoanService(new InMemoryLoanRepository());
    private static final LocalDate START = LocalDate.of(2026, 1, 1);

    private LoanResponse loan(BigDecimal principal, BigDecimal rate, int term, BigDecimal escrow) {
        CreateLoanRequest request = new CreateLoanRequest();
        request.setBorrowerName("Test Borrower");
        request.setOriginalPrincipal(principal);
        request.setAnnualRatePct(rate);
        request.setTermMonths(term);
        request.setStartDate(START);
        request.setEscrowMonthly(escrow);
        return service.createLoan(request);
    }

    private PaymentRequest payment(String amount, String date, String key) {
        PaymentRequest request = new PaymentRequest();
        request.setAmount(new BigDecimal(amount));
        request.setPaymentDate(LocalDate.parse(date));
        request.setIdempotencyKey(key);
        return request;
    }

    @Test
    void monthlyPaymentMatchesKnownAmortizationValue() {
        // $300,000 at 6.5% over 360 months: $1,896.20 (standard amortization formula).
        BigDecimal monthly = Amortization.monthlyPayment(
                new BigDecimal("300000"), new BigDecimal("6.5"), 360);
        assertEquals(new BigDecimal("1896.20"), monthly);
    }

    @Test
    void zeroRateLoanDividesPrincipalEvenly() {
        assertEquals(new BigDecimal("833.33"),
                Amortization.monthlyPayment(new BigDecimal("10000"), BigDecimal.ZERO, 12));
    }

    @Test
    void firstPaymentSplitsIntoInterestPrincipalAndEscrow() {
        LoanResponse created = loan(new BigDecimal("300000"), new BigDecimal("6.5"), 360,
                new BigDecimal("250.00"));
        assertEquals(new BigDecimal("1896.20"), created.getMonthlyPayment());
        // 1896.20 P&I + 250.00 escrow = 2146.20 total.
        PaymentResponse paid = service.applyPayment(created.getId(),
                payment("2146.20", "2026-02-01", "key-1"));
        assertEquals(new BigDecimal("1625.00"), paid.getInterestPortion());
        assertEquals(new BigDecimal("271.20"), paid.getPrincipalPortion());
        assertEquals(new BigDecimal("250.00"), paid.getEscrowPortion());
        assertEquals(new BigDecimal("299728.80"), paid.getRemainingPrincipalAfter());
    }

    @Test
    void paymentBelowInterestPlusEscrowIsRejected() {
        LoanResponse created = loan(new BigDecimal("300000"), new BigDecimal("6.5"), 360,
                new BigDecimal("250.00"));
        // Minimum due this month is 1625.00 interest + 250.00 escrow = 1875.00.
        assertThrows(InvalidPaymentException.class, () ->
                service.applyPayment(created.getId(), payment("1800.00", "2026-02-01", "key-2")));
        assertEquals(new BigDecimal("300000.00"),
                service.getLoan(created.getId()).getRemainingPrincipal());
    }

    @Test
    void extraPaymentAboveTheSplitGoesToPrincipal() {
        LoanResponse created = loan(new BigDecimal("300000"), new BigDecimal("6.5"), 360,
                new BigDecimal("250.00"));
        PaymentResponse paid = service.applyPayment(created.getId(),
                payment("3146.20", "2026-02-01", "key-3"));
        assertEquals(new BigDecimal("1271.20"), paid.getPrincipalPortion());
        assertEquals(new BigDecimal("298728.80"), paid.getRemainingPrincipalAfter());
    }

    @Test
    void idempotentReplayDoesNotMoveMoneyTwice() {
        LoanResponse created = loan(new BigDecimal("300000"), new BigDecimal("6.5"), 360,
                new BigDecimal("250.00"));
        PaymentResponse first = service.applyPayment(created.getId(),
                payment("2146.20", "2026-02-01", "key-4"));
        PaymentResponse replay = service.applyPayment(created.getId(),
                payment("2146.20", "2026-02-01", "key-4"));
        assertEquals(first.getId(), replay.getId());
        assertEquals(1, service.paymentHistory(created.getId()).size());
        assertEquals(new BigDecimal("299728.80"),
                service.getLoan(created.getId()).getRemainingPrincipal());
    }

    @Test
    void payingTheFullBalanceMarksTheLoanPaidOff() {
        LoanResponse created = loan(new BigDecimal("10000"), BigDecimal.ZERO, 12,
                BigDecimal.ZERO);
        PaymentResponse paid = service.applyPayment(created.getId(),
                payment("10000.00", "2026-02-01", "key-5"));
        assertEquals(new BigDecimal("0.00"), paid.getRemainingPrincipalAfter());
        assertEquals("PAID_OFF", service.getLoan(created.getId()).getStatus().name());
    }

    @Test
    void scheduleSumsPrincipalToTheOriginalBalanceAndEndsAtZero() {
        LoanResponse created = loan(new BigDecimal("300000"), new BigDecimal("6.5"), 360,
                BigDecimal.ZERO);
        var schedule = service.amortizationSchedule(created.getId());
        assertEquals(360, schedule.size());
        BigDecimal principalSum = schedule.stream()
                .map(e -> e.getPrincipal()).reduce(BigDecimal.ZERO, BigDecimal::add);
        assertEquals(new BigDecimal("300000.00"), principalSum);
        assertEquals(new BigDecimal("1625.00"), schedule.get(0).getInterest());
        assertEquals(new BigDecimal("271.20"), schedule.get(0).getPrincipal());
        assertEquals(new BigDecimal("0.00"), schedule.get(359).getRemainingBalance());
    }

    @Test
    void scheduleShrinksAfterPayments() {
        LoanResponse created = loan(new BigDecimal("300000"), new BigDecimal("6.5"), 360,
                new BigDecimal("250.00"));
        service.applyPayment(created.getId(), payment("2146.20", "2026-02-01", "key-6"));
        var schedule = service.amortizationSchedule(created.getId());
        assertEquals(359, schedule.size());
        assertEquals(2, schedule.get(0).getMonth());
        assertEquals(new BigDecimal("299728.80"),
                service.getLoan(created.getId()).getRemainingPrincipal());
    }

    @Test
    void escrowBalanceAccumulatesWithEachPayment() {
        LoanResponse created = loan(new BigDecimal("300000"), new BigDecimal("6.5"), 360,
                new BigDecimal("250.00"));
        service.applyPayment(created.getId(), payment("2146.20", "2026-02-01", "key-7"));
        service.applyPayment(created.getId(), payment("2146.20", "2026-03-01", "key-8"));
        var escrow = service.escrow(created.getId());
        assertEquals(new BigDecimal("500.00"), escrow.escrowBalance());
        assertEquals(new BigDecimal("250.00"), escrow.escrowMonthly());
    }

    @Test
    void delinquencyFlagsALoanWithNoPaymentInThirtyDays() {
        LoanResponse created = loan(new BigDecimal("300000"), new BigDecimal("6.5"), 360,
                BigDecimal.ZERO);
        assertFalse(service.isDelinquent(created.getId(), LocalDate.of(2026, 1, 15)));
        assertTrue(service.isDelinquent(created.getId(), LocalDate.of(2026, 3, 15)));
        assertEquals("DELINQUENT", service.getLoan(created.getId()).getStatus().name());
    }

    @Test
    void paidOffLoanIsNeverDelinquent() {
        LoanResponse created = loan(new BigDecimal("10000"), BigDecimal.ZERO, 12, BigDecimal.ZERO);
        service.applyPayment(created.getId(), payment("10000.00", "2026-02-01", "key-9"));
        assertFalse(service.isDelinquent(created.getId(), LocalDate.of(2027, 1, 1)));
    }

    @Test
    void concurrentPaymentsDoNotCorruptTheBalance() throws Exception {
        LoanResponse created = loan(new BigDecimal("300000"), new BigDecimal("6.5"), 360,
                new BigDecimal("250.00"));
        int threads = 10;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch latch = new CountDownLatch(threads);
        for (int i = 0; i < threads; i++) {
            final int n = i;
            pool.submit(() -> {
                try {
                    service.applyPayment(created.getId(),
                            payment("2146.20", "2026-02-01", "conc-" + n));
                } finally {
                    latch.countDown();
                }
            });
        }
        assertTrue(latch.await(10, TimeUnit.SECONDS));
        pool.shutdown();
        List<PaymentResponse> history = service.paymentHistory(created.getId());
        assertEquals(10, history.size());
        BigDecimal principalPaid = history.stream()
                .map(PaymentResponse::getPrincipalPortion)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        BigDecimal expected = new BigDecimal("300000.00").subtract(principalPaid);
        assertEquals(expected, service.getLoan(created.getId()).getRemainingPrincipal());
    }
}
