import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useWebSocket } from '../hooks/useWebSocket'
import { apiFetch } from '../hooks/useApi'

const API = import.meta.env.VITE_API_URL ?? ''

interface Portfolio {
  id: string
  name: string
  created_at: string
  stock_count: number
  avg_risk_score: number | null
  rec_counts: Record<string, number>
}

async function fetchPortfolios(): Promise<Portfolio[]> {
  const res = await apiFetch(`${API}/api/portfolios`)
  if (!res.ok) throw new Error('Failed to fetch portfolios')
  return res.json()
}

async function createPortfolio(name: string): Promise<Portfolio> {
  const res = await apiFetch(`${API}/api/portfolios`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error('Failed to create portfolio')
  return res.json()
}

async function deletePortfolio(id: string): Promise<void> {
  const res = await apiFetch(`${API}/api/portfolios/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete portfolio')
}

export default function Dashboard() {
  const { user } = useAuth()
  const userId = (user?.id as string) ?? null
  useWebSocket(userId, null)

  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')

  const { data: portfolios = [], isLoading, error: queryError } = useQuery({
    queryKey: ['portfolios'],
    queryFn: fetchPortfolios,
    retry: 1,
  })

  const createMutation = useMutation({
    mutationFn: createPortfolio,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolios'] })
      setCreating(false)
      setNewName('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deletePortfolio,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['portfolios'] }),
  })

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    const name = newName.trim()
    if (name) createMutation.mutate(name)
  }

  if (isLoading) return <p style={{ padding: 24, color: 'var(--color-text-sub)' }}>Loading…</p>

  if (queryError) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <p style={{ color: 'var(--color-sell)', marginBottom: 8, fontWeight: 600 }}>Failed to load portfolios</p>
        <p style={{ color: 'var(--color-text-sub)', fontSize: 13 }}>{queryError.message}</p>
      </div>
    )
  }

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, marginTop: 8 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>Portfolios</h1>
        {!creating && (
          <button className="btn-primary" onClick={() => setCreating(true)}>
            + New Portfolio
          </button>
        )}
      </div>

      {/* Inline create form */}
      {creating && (
        <form
          onSubmit={handleCreate}
          className="card"
          style={{ display: 'flex', gap: 8, padding: 12, marginBottom: 16, alignItems: 'center' }}
        >
          <input
            autoFocus
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Portfolio name…"
            style={{
              flex: 1,
              padding: '7px 12px',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              fontSize: 14,
              outline: 'none',
            }}
          />
          <button className="btn-primary" type="submit" disabled={createMutation.isPending || !newName.trim()}>
            {createMutation.isPending ? 'Creating…' : 'Create'}
          </button>
          <button
            type="button"
            onClick={() => { setCreating(false); setNewName('') }}
            style={{ background: 'none', border: 'none', color: 'var(--color-muted)', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}
          >
            ×
          </button>
        </form>
      )}

      {portfolios.length === 0 && !creating && (
        <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--color-text-sub)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📂</div>
          <p style={{ marginBottom: 16 }}>No portfolios yet.</p>
          <button className="btn-primary" onClick={() => setCreating(true)}>Create your first portfolio</button>
        </div>
      )}

      {portfolios.map((p) => {
        const score = p.avg_risk_score
        const scoreColor = score == null ? 'var(--color-muted)'
          : score < 35 ? 'var(--color-buy)'
          : score < 65 ? 'var(--color-hold)'
          : 'var(--color-sell)'
        const buy  = p.rec_counts['BUY']  ?? 0
        const hold = p.rec_counts['HOLD'] ?? 0
        const sell = p.rec_counts['SELL'] ?? 0
        const total = buy + hold + sell

        return (
          <div
            key={p.id}
            className="card"
            style={{ padding: '16px 18px', marginBottom: 12 }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ minWidth: 0 }}>
                <Link
                  to={`/portfolio/${p.id}`}
                  style={{ fontWeight: 700, fontSize: 16, color: 'var(--color-primary)' }}
                >
                  {p.name}
                </Link>
                <div style={{ fontSize: 12, color: 'var(--color-muted)', marginTop: 2 }}>
                  {p.stock_count === 0
                    ? 'No stocks yet'
                    : `${p.stock_count} stock${p.stock_count !== 1 ? 's' : ''}`}
                  {' · '}
                  Created {new Date(p.created_at).toLocaleDateString()}
                </div>
              </div>
              <button
                onClick={() => deleteMutation.mutate(p.id)}
                title="Delete portfolio"
                style={{ background: 'none', border: 'none', color: 'var(--color-muted)', cursor: 'pointer', fontSize: 18, lineHeight: 1, padding: '0 4px', flexShrink: 0 }}
              >
                ×
              </button>
            </div>

            {p.stock_count > 0 && (
              <div style={{ marginTop: 12, display: 'flex', gap: 20, alignItems: 'center', flexWrap: 'wrap' }}>
                {/* Avg risk score */}
                <div>
                  <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 3 }}>Avg Risk Score</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 80, height: 6, background: 'var(--color-border)', borderRadius: 3 }}>
                      <div style={{ width: `${score ?? 0}%`, height: '100%', background: scoreColor, borderRadius: 3, transition: 'width 0.4s' }} />
                    </div>
                    <span style={{ fontSize: 13, fontWeight: 700, color: scoreColor }}>
                      {score != null ? score.toFixed(1) : '—'}
                    </span>
                  </div>
                </div>

                {/* Signal breakdown */}
                {total > 0 && (
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 3 }}>Signals</div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      {buy > 0 && (
                        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-buy)', background: 'rgba(0,212,170,0.1)', padding: '2px 8px', borderRadius: 'var(--radius-pill)' }}>
                          {buy} BUY
                        </span>
                      )}
                      {hold > 0 && (
                        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-hold)', background: 'rgba(240,180,41,0.1)', padding: '2px 8px', borderRadius: 'var(--radius-pill)' }}>
                          {hold} HOLD
                        </span>
                      )}
                      {sell > 0 && (
                        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-sell)', background: 'rgba(255,71,87,0.1)', padding: '2px 8px', borderRadius: 'var(--radius-pill)' }}>
                          {sell} SELL
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
