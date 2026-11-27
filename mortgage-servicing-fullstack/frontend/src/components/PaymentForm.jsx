import { useState } from 'react';
import { minimumDue, splitPayment } from '../lib/amortization';

export default function PaymentForm({ loan, onPay }) {
  const [amount, setAmount] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(null);

  const due = minimumDue(loan.remainingPrincipal, loan.annualRatePct, loan.escrowMonthly);

  function submit(event) {
    event.preventDefault();
    const value = Number(amount);
    if (!Number.isFinite(value) || value < due) {
      setError(`Payment must be at least $${due.toFixed(2)} (interest + escrow this month).`);
      setDone(null);
      return;
    }
    setError('');
    const split = splitPayment(value, loan.remainingPrincipal, loan.annualRatePct, loan.escrowMonthly);
    setDone({ amount: value, ...split });
    onPay(value);
  }

  return (
    <form onSubmit={submit}>
      <h3>Make a payment</h3>
      <p>Minimum due this month: ${due.toFixed(2)} (interest + escrow).</p>
      <label>
        Amount ($)
        <input
          type="number"
          step="0.01"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
        />
      </label>
      <button type="submit">Apply payment</button>
      {error && <p role="alert">{error}</p>}
      {done && (
        <p>
          Applied ${done.amount.toFixed(2)}: ${done.principal.toFixed(2)} to principal, $
          {done.interest.toFixed(2)} interest, ${done.escrow.toFixed(2)} escrow.
        </p>
      )}
    </form>
  );
}
