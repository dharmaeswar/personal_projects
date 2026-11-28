package aml;

import java.math.BigDecimal;
import java.time.LocalDate;

/** One surveillance finding raised by a detector, ready for analyst review. */
public record Alert(
        String alertId,
        String accountId,
        LocalDate date,
        String rule,        // STRUCTURING, VELOCITY, HIGH_RISK_CORRIDOR, ROUND_AMOUNT
        String severity,    // HIGH, MEDIUM
        BigDecimal amount,  // total amount behind the finding, where it applies
        int txnCount,
        String detail) {

    public String toCsv() {
        return String.join(",", alertId, accountId, date.toString(), rule,
                severity, amount.toPlainString(), Integer.toString(txnCount),
                "\"" + detail.replace("\"", "\"\"") + "\"");
    }

    public static String csvHeader() {
        return "alert_id,account_id,date,rule,severity,amount,txn_count,detail";
    }
}
