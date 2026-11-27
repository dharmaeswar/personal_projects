package com.dharma.mortgage.model;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;

/** Pure amortization math, shared by the service and the schedule endpoint. */
public final class Amortization {
    private static final MathContext MC = new MathContext(28, RoundingMode.HALF_UP);

    private Amortization() {}

    public static BigDecimal monthlyRate(BigDecimal annualRatePct) {
        return annualRatePct.divide(new BigDecimal("100"), MC)
                .divide(new BigDecimal("12"), MC);
    }

    /** Standard formula M = P * r * (1+r)^n / ((1+r)^n - 1); P/n when the rate is 0. */
    public static BigDecimal monthlyPayment(BigDecimal principal, BigDecimal annualRatePct,
                                            int termMonths) {
        BigDecimal rate = monthlyRate(annualRatePct);
        if (rate.compareTo(BigDecimal.ZERO) == 0) {
            return principal.divide(new BigDecimal(termMonths), 2, RoundingMode.HALF_UP);
        }
        BigDecimal factor = BigDecimal.ONE.add(rate, MC).pow(termMonths, MC);
        BigDecimal payment = principal.multiply(rate, MC).multiply(factor, MC)
                .divide(factor.subtract(BigDecimal.ONE, MC), MC);
        return payment.setScale(2, RoundingMode.HALF_UP);
    }

    /** One month of interest on a balance, rounded to cents. */
    public static BigDecimal monthlyInterest(BigDecimal balance, BigDecimal annualRatePct) {
        return balance.multiply(monthlyRate(annualRatePct), MC)
                .setScale(2, RoundingMode.HALF_UP);
    }

    /**
     * Remaining schedule from a balance: one entry per month left. The final entry
     * is adjusted so the balance reaches exactly zero — no stray cents remain.
     */
    public static List<AmortizationEntry> schedule(BigDecimal balance, BigDecimal annualRatePct,
                                                   BigDecimal monthlyPayment, BigDecimal escrowMonthly,
                                                   int monthsLeft, int firstMonth) {
        List<AmortizationEntry> entries = new ArrayList<>();
        BigDecimal remaining = balance.setScale(2, RoundingMode.HALF_UP);
        for (int month = firstMonth; month < firstMonth + monthsLeft; month++) {
            if (remaining.compareTo(BigDecimal.ZERO) <= 0) {
                break;
            }
            BigDecimal interest = monthlyInterest(remaining, annualRatePct);
            BigDecimal principal = monthlyPayment.subtract(interest).setScale(2, RoundingMode.HALF_UP);
            boolean last = month == firstMonth + monthsLeft - 1 || principal.compareTo(remaining) >= 0;
            if (last) {
                principal = remaining;
            }
            BigDecimal payment = principal.add(interest).add(escrowMonthly)
                    .setScale(2, RoundingMode.HALF_UP);
            remaining = remaining.subtract(principal).setScale(2, RoundingMode.HALF_UP);
            entries.add(new AmortizationEntry(month, payment, principal, interest,
                    escrowMonthly, remaining));
            if (remaining.compareTo(BigDecimal.ZERO) == 0) {
                break;
            }
        }
        return entries;
    }

    public static BigDecimal round(BigDecimal value) {
        return value.setScale(2, RoundingMode.HALF_UP);
    }
}
