import { useState } from 'react'
import { apiPostWithRetry } from '../lib/api'

/**
 * Contact form: client-side validation first, then a POST with retries and
 * one idempotency key, so a double-click or a retried request never creates
 * a duplicate submission. Server-side 400s surface per-field messages.
 */
export default function ContactForm({ onSubmitted }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [status, setStatus] = useState('idle')

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (!name.trim() || !email.trim() || !message.trim()) {
      setError('Name, email, and message are all required.')
      return
    }
    if (!email.includes('@')) {
      setError('Enter a valid email address.')
      return
    }
    setStatus('sending')
    try {
      const result = await apiPostWithRetry('/api/forms/contact/submissions', {
        name: name.trim(),
        email: email.trim(),
        message: message.trim(),
      })
      setStatus('sent')
      onSubmitted?.(result)
    } catch (err) {
      setStatus('idle')
      setError(err.data?.fields ? `Check these fields: ${err.data.fields.join(', ')}` : err.message)
    }
  }

  if (status === 'sent') {
    return <p role="status">Thanks — your message was received.</p>
  }
  return (
    <form onSubmit={submit} aria-label="Contact form">
      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        Email
        <input type="text" inputMode="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label>
        Message
        <textarea value={message} onChange={(e) => setMessage(e.target.value)} />
      </label>
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={status === 'sending'}>
        {status === 'sending' ? 'Sending…' : 'Send message'}
      </button>
    </form>
  )
}
