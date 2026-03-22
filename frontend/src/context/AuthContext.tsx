import React, { createContext, useContext, useState, useEffect } from 'react'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// Token stored in sessionStorage so it survives page refreshes but not new tabs
const TOKEN_KEY = 'civic_auth_token'

export function getStoredToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}

function storeToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token)
}

function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY)
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
    try {
      // Try to get user with whatever auth we have (cookie or stored token)
      const token = getStoredToken()
      const headers: Record<string, string> = {}
      if (token) headers['Authorization'] = `Bearer ${token}`

      const res = await fetch(`${API_BASE}/auth/user`, {
        credentials: 'include',
        headers,
      })

      if (res.ok) {
        const data = await res.json()
        setUser(data)

        // If we don't have a stored token yet, try to fetch one from the cookie
        if (!token) {
          try {
            const tokenRes = await fetch(`${API_BASE}/auth/token`, { credentials: 'include' })
            if (tokenRes.ok) {
              const { token: t } = await tokenRes.json()
              storeToken(t)
            }
          } catch {
            // cookie-only mode is fine for local dev
          }
        }
      } else {
        setUser(null)
        clearToken()
      }
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }

  const logout = async () => {
    const token = getStoredToken()
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    await fetch(`${API_BASE}/auth/logout`, { credentials: 'include', headers })
    clearToken()
    setUser(null)
    window.location.href = '/login'
  }

  useEffect(() => { refresh() }, [])

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
