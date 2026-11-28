package aml;

import java.util.List;

/**
 * Stage 4 of the pipeline: vendor-platform export. Alerts are written out
 * as a flat alert feed in the shape a vendor surveillance platform (for
 * example NICE Actimize) ingests: one row per alert with the account, date,
 * rule, severity, amount and a free-text detail field. The pipeline does
 * not claim to run Actimize itself; it produces the feed a vendor platform
 * would consume, which is the integration point this role builds.
 */
public final class VendorExport {

    private VendorExport() {
    }

    /** Actimize-style alert feed: header + one row per alert. */
    public static String actimizeFeed(List<Alert> alerts) {
        StringBuilder sb = new StringBuilder();
        sb.append("ALERT_ID|ACCOUNT_ID|ALERT_DATE|RULE_NAME|SEVERITY|AMOUNT|TXN_COUNT|DETAIL\n");
        for (Alert a : alerts) {
            sb.append(a.alertId()).append("|").append(a.accountId()).append("|")
                    .append(a.date()).append("|").append(a.rule()).append("|")
                    .append(a.severity()).append("|").append(a.amount().toPlainString()).append("|")
                    .append(a.txnCount()).append("|")
                    .append(a.detail().replace("|", " ")).append("\n");
        }
        return sb.toString();
    }
}
