import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import FunnelPanel from './FunnelPanel';

const funnel = {
  total: 3,
  started: 1,
  submitted: 2,
  decided: 2,
  approvedOrConditional: 1,
  funded: 1,
  countsByStatus: { STARTED: 1, DENIED: 1, FUNDED: 1 },
  submissionRatePct: 66.7,
  decisionRatePct: 100.0,
  approvalRatePct: 50.0,
  fundingRatePct: 100.0,
};

describe('FunnelPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows stage counts and conversion rates', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => funnel,
    }));
    render(<FunnelPanel />);
    await waitFor(() => {
      expect(screen.getByText('3 application(s) in the funnel.')).toBeInTheDocument();
    });
    expect(screen.getByText('66.7%')).toBeInTheDocument();
    expect(screen.getByText('50.0%')).toBeInTheDocument();
    expect(screen.getByText('Funded')).toBeInTheDocument();
  });

  it('shows an empty state when there are no applications', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...funnel, total: 0, started: 0 }),
    }));
    render(<FunnelPanel />);
    await waitFor(() => {
      expect(screen.getByText(/No applications yet/)).toBeInTheDocument();
    });
  });

  it('shows an error when the funnel request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    render(<FunnelPanel />);
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Could not load the application funnel');
    });
  });
});
