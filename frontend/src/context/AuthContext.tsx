import React, { createContext, useContext, useState, useEffect } from 'react'

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

/** Returns true if the token exists and is not expired. */
function isTokenValid(token: string): boolean {
  const claims = decodeJwtPayload(token)
  if (!claims) return false
  const exp = claims.exp as number | undefined
  if (exp && Date.now() / 1000 > exp) return false
  return true
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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = async () => {
    const token = getToken()
    // Fast path: decode claims from local token without a network round-trip
    if (token && isTokenValid(token)) {
      const claims = decodeJwtPayload(token)
      if (claims) {
        setUser(claims)
        setLoading(false)
        return
      }
    }
    // No valid local token — try the server (handles cookie fallback / token refresh)
    try {
      const res = await fetch(`${API_BASE}/auth/user`, {
        credentials: 'include',
        headers: authHeaders(),
      })
      if (res.ok) {
        const data = await res.json()
        setUser(data)
      } else {
        clearToken()
        setUser(null)
      }
    } catch {
      setUser(null)
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
    // Extract token from URL fragment after OAuth callback
    const hash = window.location.hash
    if (hash.startsWith('#token=')) {
      const token = hash.slice(7)
      setToken(token)
      window.history.replaceState(null, '', window.location.pathname)
    }
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
