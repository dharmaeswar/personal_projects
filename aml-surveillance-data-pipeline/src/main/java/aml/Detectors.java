package aml;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Stage 2 of the pipeline: rule-based surveillance detectors over the clean
 * transactions. Each detector works per account per business day and raises
 * at most one alert per account per day per rule, so an analyst sees one
 * finding per pattern instead of one per transaction.
 *
 * Thresholds are the pipeline's documented parameters, not hard-coded
 * magic in the middle of the logic:
 * - STRUCTURING: 3+ cash deposits each under $10,000 (the CTR reporting
 *   threshold) on one day, totalling $25,000 or more.
 * - VELOCITY: 6+ transactions inside any 60-minute window on one day.
 * - HIGH_RISK_CORRIDOR: 2+ wires to a high-risk jurisdiction on one day.
 * - ROUND_AMOUNT: 3+ payments of exactly $5,000 on one day.
 *
 * These are screening rules that queue work for a human analyst. They do
 * not decide that money laundering happened.
 */
public final class Detectors {

    public static final BigDecimal CTR_THRESHOLD = new BigDecimal("10000");
    public static final BigDecimal STRUCTURING_TOTAL = new BigDecimal("25000");
    public static final int STRUCTURING_MIN_DEPOSITS = 3;
    public static final int VELOCITY_MIN_TXNS = 6;
    public static final int VELOCITY_WINDOW_MINUTES = 60;
    public static final int CORRIDOR_MIN_WIRES = 2;
    public static final BigDecimal ROUND_AMOUNT = new BigDecimal("5000");
    public static final int ROUND_MIN_TXNS = 3;

    /** High-risk jurisdictions for the corridor rule (demo list, seeded data). */
    public static final Set<String> HIGH_RISK_COUNTRIES = Set.of("XX", "XY");

    private Detectors() {
    }

    public static List<Alert> runAll(List<Transaction> txns) {
        return runAll(txns, 1);
    }

    /** startSeq keeps alert ids unique when batch and micro-batch runs combine. */
    public static List<Alert> runAll(List<Transaction> txns, int startSeq) {
        List<Alert> alerts = new ArrayList<>();
        Map<String, List<Transaction>> byAccountDay = new HashMap<>();
        for (Transaction t : txns) {
            byAccountDay.computeIfAbsent(t.accountId() + "|" + t.date(), k -> new ArrayList<>()).add(t);
        }
        int seq = startSeq;
        for (Map.Entry<String, List<Transaction>> e : byAccountDay.entrySet()) {
            List<Transaction> day = e.getValue();
            String account = day.get(0).accountId();
            LocalDate date = day.get(0).date();
            Alert a;
            a = structuring(account, date, day, seq);
            if (a != null) {
                alerts.add(a);
                seq++;
            }
            a = velocity(account, date, day, seq);
            if (a != null) {
                alerts.add(a);
                seq++;
            }
            a = highRiskCorridor(account, date, day, seq);
            if (a != null) {
                alerts.add(a);
                seq++;
            }
            a = roundAmount(account, date, day, seq);
            if (a != null) {
                alerts.add(a);
                seq++;
            }
        }
        alerts.sort(Comparator.comparing(Alert::date).thenComparing(Alert::accountId).thenComparing(Alert::rule));
        return alerts;
    }

    static Alert structuring(String account, LocalDate date, List<Transaction> day, int seq) {
        List<Transaction> deposits = day.stream().filter(Transaction::isCashDeposit).toList();
        BigDecimal total = deposits.stream()
                .map(Transaction::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        boolean underThreshold = deposits.stream()
                .allMatch(t -> t.amount().compareTo(CTR_THRESHOLD) < 0);
        if (deposits.size() >= STRUCTURING_MIN_DEPOSITS && underThreshold
                && total.compareTo(STRUCTURING_TOTAL) >= 0) {
            return new Alert("AL-" + seq, account, date, "STRUCTURING", "HIGH", total, deposits.size(),
                    deposits.size() + " cash deposits just under $10,000 totalling $" + total.toPlainString()
                            + " in one day; possible structuring to avoid CTR reporting");
        }
        return null;
    }

    static Alert velocity(String account, LocalDate date, List<Transaction> day, int seq) {
        List<LocalTime> times = day.stream().map(Transaction::time).sorted().toList();
        for (int i = 0; i < times.size(); i++) {
            int j = i;
            while (j < times.size()
                    && times.get(j).toSecondOfDay() - times.get(i).toSecondOfDay() < VELOCITY_WINDOW_MINUTES * 60) {
                j++;
            }
            if (j - i >= VELOCITY_MIN_TXNS) {
                return new Alert("AL-" + seq, account, date, "VELOCITY", "MEDIUM",
                        BigDecimal.ZERO, j - i,
                        (j - i) + " transactions inside " + VELOCITY_WINDOW_MINUTES
                                + " minutes starting " + times.get(i) + "; possible automated or rushed activity");
            }
        }
        return null;
    }

    static Alert highRiskCorridor(String account, LocalDate date, List<Transaction> day, int seq) {
        List<Transaction> wires = day.stream()
                .filter(t -> t.isWire() && HIGH_RISK_COUNTRIES.contains(t.counterpartyCountry()))
                .toList();
        if (wires.size() >= CORRIDOR_MIN_WIRES) {
            BigDecimal total = wires.stream().map(Transaction::amount).reduce(BigDecimal.ZERO, BigDecimal::add);
            return new Alert("AL-" + seq, account, date, "HIGH_RISK_CORRIDOR", "HIGH", total, wires.size(),
                    wires.size() + " wires to high-risk jurisdiction(s) totalling $" + total.toPlainString());
        }
        return null;
    }

    static Alert roundAmount(String account, LocalDate date, List<Transaction> day, int seq) {
        List<Transaction> rounds = day.stream()
                .filter(t -> t.type().equals("PAYMENT") && t.amount().compareTo(ROUND_AMOUNT) == 0)
                .toList();
        if (rounds.size() >= ROUND_MIN_TXNS) {
            BigDecimal total = rounds.stream().map(Transaction::amount).reduce(BigDecimal.ZERO, BigDecimal::add);
            return new Alert("AL-" + seq, account, date, "ROUND_AMOUNT", "MEDIUM", total, rounds.size(),
                    rounds.size() + " payments of exactly $" + ROUND_AMOUNT.toPlainString()
                            + " in one day; round amounts can mask the true purpose of a payment");
        }
        return null;
    }
}
