// LoginPage — render-time auth redirect, no useNavigate needed
import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export default function LoginPage() {
  const { user, loading } = useAuth()

  if (loading) return null
  if (user) return <Navigate to="/dashboard" replace />

  const handleLogin = () => {
    window.location.href = `${API_BASE}/auth/login`
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>Stock Portfolio Advisor</h1>
      <p style={{ color: 'var(--color-text-sub)', marginBottom: 24 }}>Sign in to manage your portfolio</p>
      <button
        onClick={handleLogin}
        style={{
          background: 'var(--color-primary)',
          color: '#0a1118',
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
