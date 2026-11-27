// Pure amortization math. Mirrors the backend (Amortization.java) so the
// frontend can preview schedules without a round trip; the backend stays the
// source of truth for anything that moves money.

export function monthlyRate(annualRatePct) {
  return annualRatePct / 100 / 12;
}

export function roundCents(value) {
  return Math.round(value * 100) / 100;
}

/** Standard formula M = P * r * (1+r)^n / ((1+r)^n - 1); P/n at a 0% rate. */
export function monthlyPayment(principal, annualRatePct, termMonths) {
  const r = monthlyRate(annualRatePct);
  if (r === 0) {
    return roundCents(principal / termMonths);
  }
  const factor = Math.pow(1 + r, termMonths);
  return roundCents((principal * r * factor) / (factor - 1));
}

/** One month of interest on a balance, rounded to cents. */
export function monthlyInterest(balance, annualRatePct) {
  return roundCents(balance * monthlyRate(annualRatePct));
}

/**
 * Remaining schedule from a balance. The final row is adjusted so the balance
 * reaches exactly zero — no stray cents remain.
 */
export function buildSchedule(balance, annualRatePct, payment, escrowMonthly, monthsLeft, firstMonth = 1) {
  const rows = [];
  let remaining = roundCents(balance);
  for (let month = firstMonth; month < firstMonth + monthsLeft; month += 1) {
    if (remaining <= 0) break;
    const interest = monthlyInterest(remaining, annualRatePct);
    let principal = roundCents(payment - interest);
    const last = month === firstMonth + monthsLeft - 1 || principal >= remaining;
    if (last) principal = remaining;
    const total = roundCents(principal + interest + escrowMonthly);
    remaining = roundCents(remaining - principal);
    rows.push({ month, payment: total, principal, interest, escrow: escrowMonthly, remainingBalance: remaining });
    if (remaining === 0) break;
  }
  return rows;
}

/**
 * Minimum a payment must cover this month: interest on the balance plus escrow.
 * The form refuses anything below it before it ever reaches the API.
 */
export function minimumDue(balance, annualRatePct, escrowMonthly) {
  return roundCents(monthlyInterest(balance, annualRatePct) + escrowMonthly);
}

/** Split a payment into interest / principal / escrow, like the backend does. */
export function splitPayment(amount, balance, annualRatePct, escrowMonthly) {
  const interest = monthlyInterest(balance, annualRatePct);
  const principal = Math.min(roundCents(amount - interest - escrowMonthly), balance);
  return { interest, principal, escrow: escrowMonthly };
}
