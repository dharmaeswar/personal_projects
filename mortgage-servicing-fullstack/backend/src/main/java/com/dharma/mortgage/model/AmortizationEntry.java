package com.dharma.mortgage.model;

import java.math.BigDecimal;

/** One row of an amortization schedule. */
public record AmortizationEntry(int month, BigDecimal payment, BigDecimal principal,
                                BigDecimal interest, BigDecimal escrow,
                                BigDecimal remainingBalance) {}
