import React, { createContext, useContext, useReducer, useEffect } from 'react'

interface AuthState {
  token: string | null
  userId: string | null
}

type AuthAction =
  | { type: 'LOGIN'; token: string; userId: string }
  | { type: 'LOGOUT' }

const initialState: AuthState = {
  token: sessionStorage.getItem('token'),
  userId: sessionStorage.getItem('userId'),
}

function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case 'LOGIN':
      sessionStorage.setItem('token', action.token)
      sessionStorage.setItem('userId', action.userId)
      return { token: action.token, userId: action.userId }
    case 'LOGOUT':
      sessionStorage.removeItem('token')
      sessionStorage.removeItem('userId')
      return { token: null, userId: null }
    default:
      return state
  }
}

interface AuthContextValue extends AuthState {
  login: (token: string, userId: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(authReducer, initialState)

  const login = (token: string, userId: string) =>
    dispatch({ type: 'LOGIN', token, userId })
  const logout = () => dispatch({ type: 'LOGOUT' })

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
