import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import PaymentForm from './PaymentForm';

const loan = {
  id: 'loan-1',
  remainingPrincipal: 300000,
  annualRatePct: 6.5,
  escrowMonthly: 250,
};

describe('PaymentForm', () => {
  it('shows the minimum due and refuses a short payment', async () => {
    const onPay = vi.fn();
    const user = userEvent.setup();
    render(<PaymentForm loan={loan} onPay={onPay} />);
    expect(screen.getByText(/Minimum due this month: \$1875.00/)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Amount/), '100');
    await user.click(screen.getByRole('button', { name: /Apply payment/ }));
    expect(screen.getByRole('alert')).toHaveTextContent('at least $1875.00');
    expect(onPay).not.toHaveBeenCalled();
  });

  it('applies a valid payment and shows the split', async () => {
    const onPay = vi.fn();
    const user = userEvent.setup();
    render(<PaymentForm loan={loan} onPay={onPay} />);
    await user.type(screen.getByLabelText(/Amount/), '2146.20');
    await user.click(screen.getByRole('button', { name: /Apply payment/ }));
    expect(onPay).toHaveBeenCalledWith(2146.2);
    expect(screen.getByText(/Applied \$2146.20/)).toBeInTheDocument();
    expect(screen.getByText(/\$271.20 to principal/)).toBeInTheDocument();
  });
});
