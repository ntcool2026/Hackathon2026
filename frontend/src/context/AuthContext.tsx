import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const TOKEN_KEY = 'civic_id_token'

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export { getToken }

function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** Decode JWT payload without verifying signature (client-side only). */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(payload))
  } catch {
    return null
  }
}

/** Returns true if the token parses and is not expired. Tokens without exp are accepted. */
function isTokenValid(token: string): boolean {
  const claims = decodeJwtPayload(token)
  if (!claims) return false
  const exp = claims.exp as number | undefined
  // Only reject if exp is present AND already passed
  if (exp !== undefined && Date.now() / 1000 > exp) return false
  return true
}

// ---------------------------------------------------------------------------
// Extract token from URL hash BEFORE first render so initUserFromStorage works
// on the OAuth callback redirect (/dashboard#token=...)
// ---------------------------------------------------------------------------
;(function extractTokenFromHash() {
  if (typeof window === 'undefined') return
  const hash = window.location.hash
  if (hash.startsWith('#token=')) {
    const token = hash.slice(7)
    setToken(token)
    window.history.replaceState(null, '', window.location.pathname)
  }
})()

function initUserFromStorage(): Record<string, unknown> | null {
  const token = getToken()
  if (token && isTokenValid(token)) {
    const claims = decodeJwtPayload(token)
    if (!claims) return null
    // Map sub → id to match Civic's BaseUser shape
    if (!claims.id && claims.sub) claims.id = claims.sub
    return claims
  }
  return null
}

interface AuthState {
  user: Record<string, unknown> | null
  loading: boolean
}

interface AuthContextValue extends AuthState {
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Record<string, unknown> | null>(initUserFromStorage)
  const [loading, setLoading] = useState(() => initUserFromStorage() === null)

  const refresh = async () => {
    const token = getToken()
    // If we have a valid local token, use it — no network call needed
    if (token && isTokenValid(token)) {
      const claims = decodeJwtPayload(token)
      if (claims) {
        if (!claims.id && claims.sub) claims.id = claims.sub
        setUser(claims)
        setLoading(false)
        return
      }
    }
    // No valid local token — try the server
    try {
      const res = await fetch(`${API_BASE}/auth/user`, {
        credentials: 'include',
        headers: authHeaders(),
      })
      if (res.ok) {
        const data = await res.json()
        setUser(data)
      } else {
        // Only clear token on explicit 401, not network errors
        if (res.status === 401) {
          clearToken()
          setUser(null)
        }
      }
    } catch {
      // Network error — don't clear existing auth state
    } finally {
      setLoading(false)
    }
  }

  const logout = async () => {
    clearToken()
    await fetch(`${API_BASE}/auth/logout`, { credentials: 'include', headers: authHeaders() })
    setUser(null)
    window.location.href = '/login'
  }

  useEffect(() => {
    // Hash already handled at module load time — just refresh to confirm state
    refresh()
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
