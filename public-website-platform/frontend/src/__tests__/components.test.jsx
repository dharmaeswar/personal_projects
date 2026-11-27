import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ContactForm from '../components/ContactForm'
import ConsentBanner from '../components/ConsentBanner'
import PageContent from '../components/PageContent'

describe('ConsentBanner', () => {
  it('offers accept and decline, then disappears after a choice', async () => {
    const user = userEvent.setup()
    const onChoose = vi.fn()
    render(<ConsentBanner onChoose={onChoose} />)
    await user.click(screen.getByRole('button', { name: 'Decline' }))
    expect(onChoose).toHaveBeenCalledWith({ analytics: false, marketing: false })
    expect(screen.queryByRole('region', { name: 'Cookie consent' })).not.toBeInTheDocument()
  })
})

describe('ContactForm', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('blocks submit with empty fields and shows an error', async () => {
    const user = userEvent.setup()
    render(<ContactForm />)
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(screen.getByRole('alert')).toHaveTextContent('all required')
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('blocks an invalid email before any request', async () => {
    const user = userEvent.setup()
    render(<ContactForm />)
    await user.type(screen.getByLabelText('Name'), 'Ada')
    await user.type(screen.getByLabelText('Email'), 'not-an-email')
    await user.type(screen.getByLabelText('Message'), 'Hello')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(screen.getByRole('alert')).toHaveTextContent('valid email')
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('submits once with an idempotency key and shows confirmation', async () => {
    const user = userEvent.setup()
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'sub-0001', duplicate: false }),
    })
    const onSubmitted = vi.fn()
    render(<ContactForm onSubmitted={onSubmitted} />)
    await user.type(screen.getByLabelText('Name'), 'Ada')
    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Message'), 'Hello')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(screen.getByRole('status')).toHaveTextContent('received')
    expect(onSubmitted).toHaveBeenCalledWith({ id: 'sub-0001', duplicate: false })
    const headers = global.fetch.mock.calls[0][1].headers
    expect(headers['Idempotency-Key']).toBeTruthy()
  })

  it('surfaces a server field error without crashing', async () => {
    const user = userEvent.setup()
    global.fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ error: 'missing required fields', fields: ['message'] }),
    })
    render(<ContactForm />)
    await user.type(screen.getByLabelText('Name'), 'Ada')
    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Message'), 'Hello')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('message')
  })
})

describe('PageContent', () => {
  it('renders the page title and blocks', () => {
    render(
      <PageContent
        page={{
          title: 'Ship what\'s next',
          blocks: [{ type: 'hero', heading: 'Hello', body: 'World' }],
        }}
      />,
    )
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent("Ship what's next")
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Hello')
    expect(screen.getByText('World')).toBeInTheDocument()
  })
})
