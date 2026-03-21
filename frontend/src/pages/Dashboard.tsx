import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useWebSocket } from '../hooks/useWebSocket'

const API = import.meta.env.VITE_API_URL ?? ''

interface Portfolio {
  id: string
  name: string
  created_at: string
}

async function fetchPortfolios(): Promise<Portfolio[]> {
  const res = await fetch(`${API}/api/portfolios`, { credentials: 'include' })
  if (!res.ok) throw new Error('Failed to fetch portfolios')
  return res.json()
}

async function createPortfolio(name: string): Promise<Portfolio> {
  const res = await fetch(`${API}/api/portfolios`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error('Failed to create portfolio')
  return res.json()
}

async function deletePortfolio(id: string): Promise<void> {
  const res = await fetch(`${API}/api/portfolios/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) throw new Error('Failed to delete portfolio')
}

export default function Dashboard() {
  const { userId, token } = useAuth()
  useWebSocket(userId, token)

  const queryClient = useQueryClient()
  const { data: portfolios = [], isLoading } = useQuery({
    queryKey: ['portfolios'],
    queryFn: fetchPortfolios,
  })

  const createMutation = useMutation({
    mutationFn: createPortfolio,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['portfolios'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: deletePortfolio,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['portfolios'] }),
  })

  const handleCreate = () => {
    const name = prompt('Portfolio name:')
    if (name?.trim()) createMutation.mutate(name.trim())
  }

  if (isLoading) return <p style={{ padding: 24 }}>Loading…</p>

  return (
    <div style={{ maxWidth: 700, margin: '0 auto', padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>My Portfolios</h1>
        <button
          onClick={handleCreate}
          style={{ background: '#6366f1', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 18px', cursor: 'pointer' }}
        >
          + New Portfolio
        </button>
      </div>

      {portfolios.length === 0 && (
        <p style={{ color: '#6b7280' }}>No portfolios yet. Create one to get started.</p>
      )}

      {portfolios.map((p) => (
        <div
          key={p.id}
          style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
        >
          <Link to={`/portfolio/${p.id}`} style={{ fontWeight: 600, color: '#6366f1', textDecoration: 'none', fontSize: 16 }}>
            {p.name}
          </Link>
          <button
            onClick={() => deleteMutation.mutate(p.id)}
            style={{ background: 'none', border: '1px solid #ef4444', color: '#ef4444', borderRadius: 4, padding: '4px 12px', cursor: 'pointer', fontSize: 13 }}
          >
            Delete
          </button>
        </div>
      ))}

      <div style={{ marginTop: 32, display: 'flex', gap: 12 }}>
        <Link to="/preferences" style={{ color: '#6366f1', fontSize: 14 }}>Preferences</Link>
        <Link to="/criteria" style={{ color: '#6366f1', fontSize: 14 }}>Custom Criteria</Link>
        <Link to="/thresholds" style={{ color: '#6366f1', fontSize: 14 }}>Alert Thresholds</Link>
      </div>
    </div>
  )
}
