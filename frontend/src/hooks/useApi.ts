import { getStoredToken } from '../context/AuthContext'

/**
 * Thin fetch wrapper that:
 * - Injects Authorization: Bearer header when a token is stored
 * - Handles common HTTP error codes: 401, 429, 409, 422
 */
export async function apiFetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const token = getStoredToken()
  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}

  const res = await fetch(input, {
    credentials: 'include',
    ...init,
    headers: {
      ...authHeaders,
      ...(init?.headers as Record<string, string> | undefined),
    },
  })

  if (res.status === 401) {
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
