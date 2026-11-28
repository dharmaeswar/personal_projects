package aml;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Stage 3 of the pipeline: the surveillance data model. Transactions are
 * aggregated into one row per account (the account mart) so analysts and
 * downstream jobs can query account behaviour without rescanning the raw
 * feed: transaction count, total and largest amount, cash-deposit count and
 * total, wire count and total, and the number of alerts raised.
 *
 * This is the "surveillance data model" the TD role asks for, in miniature:
 * a cleansed, modelled layer built from the raw feed, with the alert layer
 * joined on account id.
 */
public final class SurveillanceModel {

    public record AccountRow(
            String accountId,
            int txnCount,
            BigDecimal totalAmount,
            BigDecimal maxAmount,
            int cashDepositCount,
            BigDecimal cashDepositTotal,
            int wireCount,
            BigDecimal wireTotal,
            int alertCount) {

        public String toCsv() {
            return String.join(",", accountId, Integer.toString(txnCount),
                    totalAmount.toPlainString(), maxAmount.toPlainString(),
                    Integer.toString(cashDepositCount), cashDepositTotal.toPlainString(),
                    Integer.toString(wireCount), wireTotal.toPlainString(),
                    Integer.toString(alertCount));
        }

        public static String csvHeader() {
            return "account_id,txn_count,total_amount,max_amount,cash_deposit_count,"
                    + "cash_deposit_total,wire_count,wire_total,alert_count";
        }
    }

    private SurveillanceModel() {
    }

    public static List<AccountRow> build(List<Transaction> txns, List<Alert> alerts) {
        Map<String, Integer> alertsPerAccount = new HashMap<>();
        for (Alert a : alerts) {
            alertsPerAccount.merge(a.accountId(), 1, Integer::sum);
        }
        Map<String, List<Transaction>> byAccount = new HashMap<>();
        for (Transaction t : txns) {
            byAccount.computeIfAbsent(t.accountId(), k -> new ArrayList<>()).add(t);
        }
        List<AccountRow> rows = new ArrayList<>();
        for (Map.Entry<String, List<Transaction>> e : byAccount.entrySet()) {
            List<Transaction> list = e.getValue();
            BigDecimal total = BigDecimal.ZERO;
            BigDecimal max = BigDecimal.ZERO;
            BigDecimal cashTotal = BigDecimal.ZERO;
            BigDecimal wireTotal = BigDecimal.ZERO;
            int cashCount = 0;
            int wireCount = 0;
            for (Transaction t : list) {
                total = total.add(t.amount());
                if (t.amount().compareTo(max) > 0) {
                    max = t.amount();
                }
                if (t.isCashDeposit()) {
                    cashCount++;
                    cashTotal = cashTotal.add(t.amount());
                }
                if (t.isWire()) {
                    wireCount++;
                    wireTotal = wireTotal.add(t.amount());
                }
            }
            rows.add(new AccountRow(e.getKey(), list.size(), total, max, cashCount, cashTotal,
                    wireCount, wireTotal, alertsPerAccount.getOrDefault(e.getKey(), 0)));
        }
        rows.sort((a, b) -> a.accountId().compareTo(b.accountId()));
        return rows;
    }
}
