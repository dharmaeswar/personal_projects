package com.dharma.banking.model;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.UUID;

/** One immutable money movement on an account. */
public class Transaction {
    private final String id;
    private final TransactionType type;
    private final BigDecimal amount;
    private final String memo;
    private final Instant createdAt;

    public Transaction(TransactionType type, BigDecimal amount, String memo) {
        this.id = UUID.randomUUID().toString();
        this.type = type;
        this.amount = amount.setScale(2, RoundingMode.HALF_UP);
        this.memo = memo;
        this.createdAt = Instant.now();
    }

    public String getId() { return id; }
    public TransactionType getType() { return type; }
    public BigDecimal getAmount() { return amount; }
    public String getMemo() { return memo; }
    public Instant getCreatedAt() { return createdAt; }
}
