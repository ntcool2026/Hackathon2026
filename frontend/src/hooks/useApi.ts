/**
 * Thin fetch wrapper that handles common HTTP error codes:
 * - 401 → redirect to /login
 * - 429 → throw with retry message
 * - 409 → throw with limit message
 * - 422 → throw with validation detail
 */
export async function apiFetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const res = await fetch(input, { credentials: 'include', ...init })

  if (res.status === 401) {
    sessionStorage.removeItem('token')
    sessionStorage.removeItem('userId')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }

  if (res.status === 429) {
    const retryAfter = res.headers.get('Retry-After')
    throw new Error(
      retryAfter
        ? `Rate limit exceeded. Please retry after ${retryAfter} seconds.`
        : 'Rate limit exceeded. Please try again shortly.'
    )
  }

  if (res.status === 409) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail ?? 'Limit reached. Please remove an item before adding more.')
  }

  if (res.status === 422) {
    const data = await res.json().catch(() => ({}))
    const detail = Array.isArray(data.detail)
      ? data.detail.map((d: { msg: string }) => d.msg).join(', ')
      : (data.detail ?? 'Validation error')
    throw new Error(detail)
  }

  return res
}
