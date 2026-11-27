export default function AmortizationTable({ rows }) {
  if (rows.length === 0) {
    return <p>No schedule rows — this loan is paid off.</p>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>Month</th>
          <th>Payment</th>
          <th>Principal</th>
          <th>Interest</th>
          <th>Escrow</th>
          <th>Remaining</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.month}>
            <td>{row.month}</td>
            <td>${row.payment.toFixed(2)}</td>
            <td>${row.principal.toFixed(2)}</td>
            <td>${row.interest.toFixed(2)}</td>
            <td>${row.escrow.toFixed(2)}</td>
            <td>${row.remainingBalance.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
