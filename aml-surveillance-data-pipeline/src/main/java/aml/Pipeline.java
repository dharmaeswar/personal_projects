package aml;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.List;

/**
 * Pipeline driver. Two runs, mirroring how the TD role works:
 *
 * 1. Batch run over data/transactions_batch1.csv — the daily batch feed:
 *    ingest, data-quality checks with quarantine, detectors, account mart,
 *    vendor alert feed.
 * 2. Micro-batch run over data/transactions_batch2.csv — the near-real-time
 *    feed: the same stages over the new file only, appended to the same
 *    outputs, so the batch and streaming paths share one code path.
 *
 * Outputs land in output/: alerts.csv, account_mart.csv, quarantine.csv,
 * vendor_actimize_feed.txt. A run summary is printed to stdout.
 *
 * Usage: java -cp out aml.Pipeline [batch-file] [micro-batch-file]
 * Defaults: data/transactions_batch1.csv data/transactions_batch2.csv
 */
public final class Pipeline {

    private Pipeline() {
    }

    public static void main(String[] args) throws IOException {
        Path batchFile = Path.of(args.length > 0 ? args[0] : "data/transactions_batch1.csv");
        Path microFile = Path.of(args.length > 1 ? args[1] : "data/transactions_batch2.csv");
        Path outDir = Path.of("output");
        Files.createDirectories(outDir);

        List<Transaction> allClean = new ArrayList<>();
        List<Alert> allAlerts = new ArrayList<>();
        List<String> quarantineLines = new ArrayList<>();
        quarantineLines.add("txn_id,account_id,date,time,type,amount,currency,channel,country,counterparty_country,reason");

        int totalRows = 0;
        int nextAlertSeq = 1;
        for (Path file : List.of(batchFile, microFile)) {
            List<String> lines = Files.readAllLines(file);
            List<String> rows = lines.subList(1, lines.size()); // skip header
            totalRows += rows.size();
            DataQuality.Result checked = DataQuality.check(rows);
            allClean.addAll(checked.clean());
            for (DataQuality.CheckedRow q : checked.quarantined()) {
                quarantineLines.add(q.rawLine() + ",\"" + q.quarantineReason().replace("\"", "\"\"") + "\"");
            }
            List<Alert> alerts = Detectors.runAll(checked.clean(), nextAlertSeq);
            nextAlertSeq += alerts.size();
            allAlerts.addAll(alerts);
            System.out.println(file.getFileName() + ": " + rows.size() + " rows in, "
                    + checked.clean().size() + " clean, " + checked.quarantined().size()
                    + " quarantined, " + alerts.size() + " alerts");
        }

        List<SurveillanceModel.AccountRow> mart = SurveillanceModel.build(allClean, allAlerts);

        List<String> alertLines = new ArrayList<>();
        alertLines.add(Alert.csvHeader());
        allAlerts.forEach(a -> alertLines.add(a.toCsv()));
        Files.write(outDir.resolve("alerts.csv"), alertLines);

        List<String> martLines = new ArrayList<>();
        martLines.add(SurveillanceModel.AccountRow.csvHeader());
        mart.forEach(r -> martLines.add(r.toCsv()));
        Files.write(outDir.resolve("account_mart.csv"), martLines);

        Files.write(outDir.resolve("quarantine.csv"), quarantineLines);
        Files.writeString(outDir.resolve("vendor_actimize_feed.txt"),
                VendorExport.actimizeFeed(allAlerts), StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);

        System.out.println("TOTAL: " + totalRows + " rows in, " + allClean.size() + " clean, "
                + (totalRows - allClean.size()) + " quarantined, " + allAlerts.size() + " alerts, "
                + mart.size() + " accounts in mart");
        System.out.println("Outputs written to output/ (alerts.csv, account_mart.csv, quarantine.csv, vendor_actimize_feed.txt)");
    }
}
