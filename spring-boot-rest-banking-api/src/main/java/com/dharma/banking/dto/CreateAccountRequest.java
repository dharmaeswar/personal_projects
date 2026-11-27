package com.dharma.banking.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.math.BigDecimal;

public class CreateAccountRequest {
    @NotBlank(message = "ownerName is required")
    private String ownerName;

    @NotBlank(message = "accountType is required")
    @Pattern(regexp = "CHECKING|SAVINGS", message = "accountType must be CHECKING or SAVINGS")
    private String accountType;

    @NotNull(message = "openingBalance is required")
    @DecimalMin(value = "0.00", message = "openingBalance must be zero or more")
    private BigDecimal openingBalance;

    public String getOwnerName() { return ownerName; }
    public void setOwnerName(String ownerName) { this.ownerName = ownerName; }
    public String getAccountType() { return accountType; }
    public void setAccountType(String accountType) { this.accountType = accountType; }
    public BigDecimal getOpeningBalance() { return openingBalance; }
    public void setOpeningBalance(BigDecimal openingBalance) { this.openingBalance = openingBalance; }
}
