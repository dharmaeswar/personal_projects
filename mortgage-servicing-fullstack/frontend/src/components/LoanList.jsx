export default function LoanList({ loans, selectedId, onSelect }) {
  if (loans.length === 0) {
    return <p>No loans yet. Create one to start servicing it.</p>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>Borrower</th>
          <th>Principal</th>
          <th>Remaining</th>
          <th>Rate</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {loans.map((loan) => (
          <tr
            key={loan.id}
            onClick={() => onSelect(loan.id)}
            className={loan.id === selectedId ? 'selected' : ''}
          >
            <td>{loan.borrowerName}</td>
            <td>${loan.originalPrincipal.toFixed(2)}</td>
            <td>${loan.remainingPrincipal.toFixed(2)}</td>
            <td>{loan.annualRatePct}%</td>
            <td>{loan.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
