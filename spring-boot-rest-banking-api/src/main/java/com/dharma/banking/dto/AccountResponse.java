package com.dharma.banking.dto;

import com.dharma.banking.model.Account;
import java.math.BigDecimal;
import java.time.Instant;

public class AccountResponse {
    private final String id;
    private final String ownerName;
    private final String accountType;
    private final BigDecimal balance;
    private final Instant createdAt;

    public AccountResponse(Account account) {
        this.id = account.getId();
        this.ownerName = account.getOwnerName();
        this.accountType = account.getAccountType();
        this.balance = account.getBalance();
        this.createdAt = account.getCreatedAt();
    }

    public String getId() { return id; }
    public String getOwnerName() { return ownerName; }
    public String getAccountType() { return accountType; }
    public BigDecimal getBalance() { return balance; }
    public Instant getCreatedAt() { return createdAt; }
}
