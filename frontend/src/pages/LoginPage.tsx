import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

export default function LoginPage() {
  const { token } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (token) navigate('/dashboard', { replace: true })
  }, [token, navigate])

  const handleLogin = () => {
    // Redirect to Civic Auth login — the backend handles the OAuth flow
    window.location.href = `${API_BASE}/auth/login`
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>Stock Portfolio Advisor</h1>
      <p style={{ color: '#6b7280', marginBottom: 24 }}>Sign in to manage your portfolio</p>
      <button
        onClick={handleLogin}
        style={{
          background: '#6366f1',
          color: '#fff',
          border: 'none',
          borderRadius: 6,
          padding: '10px 28px',
          fontSize: 16,
          cursor: 'pointer',
          fontWeight: 600,
        }}
      >
        Sign in with Civic
      </button>
    </div>
  )
}
