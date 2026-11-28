package aml;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalTime;

/**
 * One payment / deposit / withdrawal record, as it arrives from an upstream
 * bank system (core banking feed, wire feed, branch channel). Amounts are
 * BigDecimal so money arithmetic is exact; dates and times stay separate so
 * the detectors can group by business day and by 60-minute windows.
 */
public record Transaction(
        String txnId,
        String accountId,
        LocalDate date,
        LocalTime time,
        String type,          // DEPOSIT, WITHDRAWAL, PAYMENT, TRANSFER
        BigDecimal amount,
        String currency,
        String channel,       // BRANCH, ONLINE, WIRE
        String country,
        String counterpartyCountry) {

    /** Parse one CSV data row (header excluded). Throws on a malformed row. */
    public static Transaction parse(String line) {
        String[] f = line.split(",", -1);
        if (f.length != 10) {
            throw new IllegalArgumentException("expected 10 fields, got " + f.length + ": " + line);
        }
        return new Transaction(
                f[0].trim(), f[1].trim(),
                LocalDate.parse(f[2].trim()), LocalTime.parse(f[3].trim()),
                f[4].trim(), new BigDecimal(f[5].trim()), f[6].trim(),
                f[7].trim(), f[8].trim(), f[9].trim());
    }

    public boolean isCashDeposit() {
        return type.equals("DEPOSIT") && channel.equals("BRANCH");
    }

    public boolean isWire() {
        return channel.equals("WIRE");
    }
}
