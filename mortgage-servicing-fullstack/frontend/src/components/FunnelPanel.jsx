import { useEffect, useState } from 'react';

// Borrower application funnel: counts per stage plus the conversion rate
// between stages, served by GET /api/applications/funnel. Shows where
// applications drop off between intake, decisioning, closing and funding.
export default function FunnelPanel() {
  const [funnel, setFunnel] = useState(null);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    fetch('/api/applications/funnel')
      .then((response) => {
        if (!response.ok) throw new Error(`Funnel request failed: ${response.status}`);
        return response.json();
      })
      .then(setFunnel)
      .catch((err) => setLoadError(err.message));
  }, []);

  if (loadError) {
    return <p role="alert">Could not load the application funnel: {loadError}</p>;
  }
  if (!funnel) {
    return <p>Loading application funnel…</p>;
  }
  if (funnel.total === 0) {
    return <p>No applications yet. Create one to start the funnel.</p>;
  }

  const stages = [
    ['Started', funnel.started, null],
    ['Submitted', funnel.submitted, funnel.submissionRatePct],
    ['Decided', funnel.decided, funnel.decisionRatePct],
    ['Approved or conditional', funnel.approvedOrConditional, funnel.approvalRatePct],
    ['Funded', funnel.funded, funnel.fundingRatePct],
  ];

  return (
    <section>
      <h2>Application funnel</h2>
      <p>{funnel.total} application(s) in the funnel.</p>
      <table>
        <thead>
          <tr>
            <th>Stage</th>
            <th>Count</th>
            <th>Conversion</th>
          </tr>
        </thead>
        <tbody>
          {stages.map(([stage, count, rate]) => (
            <tr key={stage}>
              <td>{stage}</td>
              <td>{count}</td>
              <td>{rate === null ? '—' : `${rate.toFixed(1)}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
