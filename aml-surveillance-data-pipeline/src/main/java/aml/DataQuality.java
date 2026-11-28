package aml;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Stage 1 of the pipeline: data-quality checks on the raw feed.
 *
 * A row is quarantined (never loaded into the surveillance model) when it
 * fails any check below; the reason is kept so an analyst can fix and
 * re-feed the row instead of silently dropping it.
 *
 * Checks: 10 fields present; amount parses and is positive; date/time parse;
 * transaction id is unique within the file (a duplicate id is a re-fed row,
 * not a second transaction).
 */
public final class DataQuality {

    public record CheckedRow(Transaction txn, String rawLine, String quarantineReason) {
        public boolean isClean() {
            return quarantineReason == null;
        }
    }

    public record Result(List<Transaction> clean, List<CheckedRow> quarantined) {
    }

    private DataQuality() {
    }

    public static Result check(List<String> lines) {
        List<Transaction> clean = new ArrayList<>();
        List<CheckedRow> quarantined = new ArrayList<>();
        Set<String> seenIds = new HashSet<>();
        for (String line : lines) {
            if (line.isBlank()) {
                continue;
            }
            String[] f = line.split(",", -1);
            String reason = null;
            Transaction txn = null;
            if (f.length != 10) {
                reason = "wrong field count: " + f.length;
            } else if (f[5].isBlank()) {
                reason = "missing amount";
            } else {
                try {
                    txn = Transaction.parse(line);
                    if (txn.amount().compareTo(BigDecimal.ZERO) <= 0) {
                        reason = "non-positive amount: " + txn.amount().toPlainString();
                    } else if (!seenIds.add(txn.txnId())) {
                        reason = "duplicate txn_id: " + txn.txnId();
                    }
                } catch (Exception e) {
                    reason = "unparseable row: " + e.getMessage();
                }
            }
            if (reason == null) {
                clean.add(txn);
            } else {
                quarantined.add(new CheckedRow(txn, line, reason));
            }
        }
        return new Result(clean, quarantined);
    }
}
