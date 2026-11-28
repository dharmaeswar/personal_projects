package aml;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.List;

/**
 * Test harness. Plain JDK, no test framework dependency: each check is an
 * assertion run with `java -ea`, and the runner prints a pass/fail count.
 * Every expected value below was hand-computed from the input rows in the
 * test itself — no value was copied from a program run.
 *
 * Run: ./build.sh  (compiles main + tests, runs this harness, then the demo)
 */
public final class AmlPipelineTest {

    private static int passed = 0;
    private static int failed = 0;

    private static void check(String name, boolean cond) {
        if (cond) {
            passed++;
            System.out.println("  PASS " + name);
        } else {
            failed++;
            System.out.println("  FAIL " + name);
        }
    }

    private static Transaction txn(String id, String acct, String date, String time,
                                   String type, String amount, String channel, String cpty) {
        return new Transaction(id, acct, LocalDate.parse(date), LocalTime.parse(time),
                type, new BigDecimal(amount), "USD", channel, "US", cpty);
    }

    public static void main(String[] args) {
        testStructuring();
        testStructuringBelowThreshold();
        testVelocity();
        testVelocityBelowThreshold();
        testHighRiskCorridor();
        testRoundAmount();
        testDataQuality();
        testAccountMart();

        System.out.println("\n" + passed + " passed, " + failed + " failed");
        if (failed > 0) {
            System.exit(1);
        }
    }

    private static void testStructuring() {
        // 4 cash deposits, each under $10,000, totalling 9800+9500+9900+9700 = 38,900
        List<Transaction> day = List.of(
                txn("T1", "A1", "2026-11-20", "09:05", "DEPOSIT", "9800", "BRANCH", "US"),
                txn("T2", "A1", "2026-11-20", "10:20", "DEPOSIT", "9500", "BRANCH", "US"),
                txn("T3", "A1", "2026-11-20", "13:40", "DEPOSIT", "9900", "BRANCH", "US"),
                txn("T4", "A1", "2026-11-20", "15:55", "DEPOSIT", "9700", "BRANCH", "US"));
        List<Alert> alerts = Detectors.runAll(day);
        check("structuring: 1 alert", alerts.size() == 1);
        check("structuring: rule name", alerts.get(0).rule().equals("STRUCTURING"));
        check("structuring: total 38900", alerts.get(0).amount().compareTo(new BigDecimal("38900")) == 0);
        check("structuring: 4 txns", alerts.get(0).txnCount() == 4);
        check("structuring: HIGH severity", alerts.get(0).severity().equals("HIGH"));
        // Alert ids continue from a given sequence so batch + micro-batch never collide.
        List<Alert> continued = Detectors.runAll(day, 5);
        check("structuring: ids continue from startSeq", continued.get(0).alertId().equals("AL-5"));
    }

    private static void testStructuringBelowThreshold() {
        // Only 2 cash deposits: no alert, however large the total.
        List<Transaction> day = List.of(
                txn("T1", "A1", "2026-11-20", "09:05", "DEPOSIT", "9900", "BRANCH", "US"),
                txn("T2", "A1", "2026-11-20", "10:20", "DEPOSIT", "9900", "BRANCH", "US"));
        check("structuring: 2 deposits raise nothing", Detectors.runAll(day).isEmpty());
        // One deposit at exactly $10,000 breaks the under-threshold condition.
        List<Transaction> day2 = List.of(
                txn("T1", "A1", "2026-11-20", "09:05", "DEPOSIT", "10000", "BRANCH", "US"),
                txn("T2", "A1", "2026-11-20", "10:20", "DEPOSIT", "9900", "BRANCH", "US"),
                txn("T3", "A1", "2026-11-20", "13:40", "DEPOSIT", "9900", "BRANCH", "US"));
        check("structuring: $10,000 deposit breaks the pattern", Detectors.runAll(day2).isEmpty());
    }

    private static void testVelocity() {
        // 6 payments inside 50 minutes (09:02-09:52) -> 1 alert, count 6.
        List<Transaction> day = new ArrayList<>();
        String[] times = {"09:02", "09:08", "09:15", "09:21", "09:29", "09:52"};
        for (int i = 0; i < times.length; i++) {
            day.add(txn("V" + i, "A2", "2026-11-21", times[i], "PAYMENT", "200", "ONLINE", "US"));
        }
        List<Alert> alerts = Detectors.runAll(day);
        check("velocity: 1 alert", alerts.size() == 1);
        check("velocity: rule name", alerts.get(0).rule().equals("VELOCITY"));
        check("velocity: 6 txns in window", alerts.get(0).txnCount() == 6);
    }

    private static void testVelocityBelowThreshold() {
        // 5 payments in the same window: below the 6-transaction minimum.
        List<Transaction> day = new ArrayList<>();
        String[] times = {"09:02", "09:08", "09:15", "09:21", "09:29"};
        for (int i = 0; i < times.length; i++) {
            day.add(txn("V" + i, "A2", "2026-11-21", times[i], "PAYMENT", "200", "ONLINE", "US"));
        }
        check("velocity: 5 txns raise nothing", Detectors.runAll(day).isEmpty());
    }

    private static void testHighRiskCorridor() {
        List<Transaction> day = List.of(
                txn("W1", "A3", "2026-11-21", "11:00", "PAYMENT", "4200", "WIRE", "XX"),
                txn("W2", "A3", "2026-11-21", "14:30", "PAYMENT", "6100", "WIRE", "XX"),
                txn("W3", "A3", "2026-11-21", "16:10", "PAYMENT", "3800", "WIRE", "US"));
        List<Alert> alerts = Detectors.runAll(day);
        check("corridor: 1 alert", alerts.size() == 1);
        check("corridor: rule name", alerts.get(0).rule().equals("HIGH_RISK_CORRIDOR"));
        // Only the two XX wires count: 4200 + 6100 = 10,300.
        check("corridor: total 10300", alerts.get(0).amount().compareTo(new BigDecimal("10300")) == 0);
        check("corridor: 2 txns", alerts.get(0).txnCount() == 2);
    }

    private static void testRoundAmount() {
        List<Transaction> day = List.of(
                txn("R1", "A4", "2026-11-22", "10:00", "PAYMENT", "5000", "ONLINE", "US"),
                txn("R2", "A4", "2026-11-22", "12:00", "PAYMENT", "5000", "ONLINE", "US"),
                txn("R3", "A4", "2026-11-22", "14:00", "PAYMENT", "5000", "ONLINE", "US"));
        List<Alert> alerts = Detectors.runAll(day);
        check("round-amount: 1 alert", alerts.size() == 1);
        check("round-amount: total 15000", alerts.get(0).amount().compareTo(new BigDecimal("15000")) == 0);
        // Two round payments only: no alert.
        List<Transaction> day2 = day.subList(0, 2);
        check("round-amount: 2 payments raise nothing", Detectors.runAll(day2).isEmpty());
    }

    private static void testDataQuality() {
        List<String> rows = List.of(
                "T1,A1,2026-11-20,09:05,DEPOSIT,9800,USD,BRANCH,US,US",
                "T2,A1,2026-11-20,10:20,PAYMENT,,USD,ONLINE,US,US",
                "T3,A1,2026-11-20,11:00,DEPOSIT,-250,USD,BRANCH,US,US",
                "T1,A1,2026-11-20,09:05,DEPOSIT,9800,USD,BRANCH,US,US",
                "T5,A1,2026-11-20,12:00,PAYMENT,100,USD,ONLINE,US");
        DataQuality.Result r = DataQuality.check(rows);
        check("dq: 1 clean row", r.clean().size() == 1);
        check("dq: 4 quarantined", r.quarantined().size() == 4);
        check("dq: missing amount flagged",
                r.quarantined().stream().anyMatch(q -> q.quarantineReason().contains("missing amount")));
        check("dq: negative amount flagged",
                r.quarantined().stream().anyMatch(q -> q.quarantineReason().contains("non-positive amount")));
        check("dq: duplicate id flagged",
                r.quarantined().stream().anyMatch(q -> q.quarantineReason().contains("duplicate txn_id")));
        check("dq: short row flagged",
                r.quarantined().stream().anyMatch(q -> q.quarantineReason().contains("wrong field count")));
    }

    private static void testAccountMart() {
        // 3 txns: 100 + 200 + 300 = 600 total, max 300, 1 cash deposit of 100.
        List<Transaction> txns = List.of(
                txn("M1", "A5", "2026-11-22", "09:00", "DEPOSIT", "100", "BRANCH", "US"),
                txn("M2", "A5", "2026-11-22", "10:00", "PAYMENT", "200", "ONLINE", "US"),
                txn("M3", "A5", "2026-11-22", "11:00", "PAYMENT", "300", "WIRE", "US"));
        List<SurveillanceModel.AccountRow> mart = SurveillanceModel.build(txns, List.of());
        check("mart: 1 account row", mart.size() == 1);
        SurveillanceModel.AccountRow row = mart.get(0);
        check("mart: 3 txns", row.txnCount() == 3);
        check("mart: total 600", row.totalAmount().compareTo(new BigDecimal("600")) == 0);
        check("mart: max 300", row.maxAmount().compareTo(new BigDecimal("300")) == 0);
        check("mart: 1 cash deposit of 100",
                row.cashDepositCount() == 1 && row.cashDepositTotal().compareTo(new BigDecimal("100")) == 0);
        check("mart: 1 wire of 300",
                row.wireCount() == 1 && row.wireTotal().compareTo(new BigDecimal("300")) == 0);
        check("mart: 0 alerts", row.alertCount() == 0);
    }
}
