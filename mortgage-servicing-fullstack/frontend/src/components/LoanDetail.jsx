import { useEffect, useState } from 'react';
import AmortizationTable from './AmortizationTable';
import PaymentForm from './PaymentForm';

export default function LoanDetail({ loan }) {
  const [schedule, setSchedule] = useState([]);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    fetch(`/api/loans/${loan.id}/schedule`)
      .then((response) => {
        if (!response.ok) throw new Error(`Schedule request failed: ${response.status}`);
        return response.json();
      })
      .then(setSchedule)
      .catch((err) => setLoadError(err.message));
  }, [loan.id]);

  function handlePay(amount) {
    fetch(`/api/loans/${loan.id}/payments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        amount,
        paymentDate: new Date().toISOString().slice(0, 10),
        idempotencyKey: `${loan.id}-${Date.now()}`,
      }),
    }).catch(() => setLoadError('Payment request failed. Try again.'));
  }

  return (
    <section>
      <h2>{loan.borrowerName}</h2>
      <p>
        Remaining ${loan.remainingPrincipal.toFixed(2)} of $
        {loan.originalPrincipal.toFixed(2)} at {loan.annualRatePct}% — $
        {loan.monthlyPayment.toFixed(2)}/mo P&amp;I, ${loan.escrowMonthly.toFixed(2)}/mo escrow.
        Escrow balance ${loan.escrowBalance.toFixed(2)}. Status: {loan.status}.
      </p>
      <PaymentForm loan={loan} onPay={handlePay} />
      <h3>Amortization schedule</h3>
      {loadError ? <p role="alert">{loadError}</p> : <AmortizationTable rows={schedule} />}
    </section>
  );
}
