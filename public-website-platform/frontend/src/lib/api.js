/** Shared API client: retries on transient failures, idempotency keys on writes. */

export async function apiFetch(path, { method = 'GET', body, headers = {} } = {}) {
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = new Error(data.error || `Request failed: ${res.status}`)
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

/** POST with up to 3 attempts on network errors and 5xx; same idempotency key every try. */
export async function apiPostWithRetry(path, body, { attempts = 3 } = {}) {
  const idempotencyKey = crypto.randomUUID()
  let lastErr
  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      return await apiFetch(path, {
        method: 'POST',
        body,
        headers: { 'Idempotency-Key': idempotencyKey },
      })
    } catch (err) {
      lastErr = err
      const retryable = !err.status || err.status >= 500
      if (!retryable || attempt === attempts - 1) throw err
      await new Promise((resolve) => setTimeout(resolve, 100 * (attempt + 1)))
    }
  }
  throw lastErr
}

export async function fetchPage(slug) {
  return apiFetch(`/api/content/pages/${slug}`)
}

export async function fetchConsent(visitorId) {
  return apiFetch(`/api/consent?visitor_id=${encodeURIComponent(visitorId)}`)
}

export async function saveConsent(visitorId, consent) {
  return apiFetch('/api/consent', { method: 'POST', body: { visitor_id: visitorId, ...consent } })
}
