import { useEffect, useState } from 'react';
import LoanDetail from './components/LoanDetail';
import LoanList from './components/LoanList';

export default function App() {
  const [loans, setLoans] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    fetch('/api/loans')
      .then((response) => {
        if (!response.ok) throw new Error(`Loans request failed: ${response.status}`);
        return response.json();
      })
      .then((data) => {
        setLoans(data);
        if (data.length > 0) setSelectedId(data[0].id);
      })
      .catch((err) => setLoadError(err.message));
  }, []);

  const selected = loans.find((loan) => loan.id === selectedId) ?? null;

  return (
    <main>
      <h1>Mortgage Servicing</h1>
      {loadError && <p role="alert">Could not load loans: {loadError}</p>}
      <LoanList loans={loans} selectedId={selectedId} onSelect={setSelectedId} />
      {selected && <LoanDetail loan={selected} />}
    </main>
  );
}
