package com.dharma.banking.dto;

import com.dharma.banking.model.Transaction;
import java.math.BigDecimal;
import java.time.Instant;

public class TransactionResponse {
    private final String id;
    private final String type;
    private final BigDecimal amount;
    private final String memo;
    private final Instant createdAt;

    public TransactionResponse(Transaction transaction) {
        this.id = transaction.getId();
        this.type = transaction.getType().name();
        this.amount = transaction.getAmount();
        this.memo = transaction.getMemo();
        this.createdAt = transaction.getCreatedAt();
    }

    public String getId() { return id; }
    public String getType() { return type; }
    public BigDecimal getAmount() { return amount; }
    public String getMemo() { return memo; }
    public Instant getCreatedAt() { return createdAt; }
}
