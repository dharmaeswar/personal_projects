package com.dharma.banking.model;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

/** A retail banking account. Money is always BigDecimal, scale 2 — never double. */
public class Account {
    private final String id;
    private final String ownerName;
    private final String accountType;
    private BigDecimal balance;
    private final Instant createdAt;
    private final List<Transaction> transactions = new ArrayList<>();

    public Account(String ownerName, String accountType, BigDecimal openingBalance) {
        this.id = UUID.randomUUID().toString();
        this.ownerName = ownerName;
        this.accountType = accountType;
        this.balance = openingBalance.setScale(2, RoundingMode.HALF_UP);
        this.createdAt = Instant.now();
        if (balance.compareTo(BigDecimal.ZERO) > 0) {
            transactions.add(new Transaction(TransactionType.DEPOSIT, balance, "Opening balance"));
        }
    }

    public String getId() { return id; }
    public String getOwnerName() { return ownerName; }
    public String getAccountType() { return accountType; }
    public synchronized BigDecimal getBalance() { return balance; }
    public Instant getCreatedAt() { return createdAt; }
    public synchronized List<Transaction> getTransactions() {
        return Collections.unmodifiableList(new ArrayList<>(transactions));
    }

    /** Applies a signed amount and records the transaction. Caller must hold the lock. */
    public synchronized void apply(TransactionType type, BigDecimal signedAmount, String memo) {
        balance = balance.add(signedAmount).setScale(2, RoundingMode.HALF_UP);
        transactions.add(new Transaction(type, signedAmount, memo));
    }
}
