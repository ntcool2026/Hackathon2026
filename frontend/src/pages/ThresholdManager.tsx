import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

const API = import.meta.env.VITE_API_URL ?? ''

interface Threshold {
  id: string
  ticker: string
  threshold: number
}

async function fetchThresholds(): Promise<Threshold[]> {
  const res = await fetch(`${API}/api/thresholds`, { credentials: 'include' })
  if (!res.ok) throw new Error('Failed to fetch thresholds')
  return res.json()
}

async function upsertThreshold(ticker: string, threshold: number): Promise<void> {
  const res = await fetch(`${API}/api/thresholds`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticker, threshold }),
  })
  if (!res.ok) throw new Error('Failed to save threshold')
}

async function deleteThreshold(ticker: string): Promise<void> {
  const res = await fetch(`${API}/api/thresholds/${ticker}`, { method: 'DELETE', credentials: 'include' })
  if (!res.ok) throw new Error('Failed to delete threshold')
}

export default function ThresholdManager() {
  const queryClient = useQueryClient()
  const [ticker, setTicker] = useState('')
  const [value, setValue] = useState('75')
  const [error, setError] = useState<string | null>(null)

  const { data: thresholds = [] } = useQuery({ queryKey: ['thresholds'], queryFn: fetchThresholds })

  const upsertMutation = useMutation({
    mutationFn: () => upsertThreshold(ticker.toUpperCase(), Number(value)),
    onSuccess: () => {
      setTicker('')
      setValue('75')
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['thresholds'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteThreshold,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['thresholds'] }),
  })

  const handleSubmit = (e: { preventDefault: () => void }) => {
    e.preventDefault()
    if (!ticker.trim()) { setError('Ticker is required'); return }
    const num = Number(value)
    if (isNaN(num) || num < 0 || num > 100) { setError('Threshold must be 0–100'); return }
    upsertMutation.mutate()
  }

  return (
    <div style={{ maxWidth: 600, margin: '0 auto', padding: 24 }}>
      <Link to="/dashboard" style={{ color: '#6366f1', fontSize: 14 }}>← Back</Link>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginTop: 12, marginBottom: 20 }}>Alert Thresholds</h1>
      <p style={{ color: '#6b7280', fontSize: 14, marginBottom: 16 }}>
        Get notified when a stock's risk score crosses your threshold.
      </p>

      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <input
          placeholder="Ticker"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          style={{ flex: 1, padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14 }}
        />
        <input
          type="number" min={0} max={100} placeholder="Threshold (0–100)"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          style={{ width: 160, padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14 }}
        />
        <button type="submit" disabled={upsertMutation.isPending}
          style={{ background: '#6366f1', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 18px', cursor: 'pointer' }}>
          Set
        </button>
      </form>
      {error && <p style={{ color: '#ef4444', fontSize: 13, marginBottom: 12 }}>{error}</p>}

      {thresholds.length === 0 && <p style={{ color: '#6b7280' }}>No thresholds set.</p>}

      {thresholds.map((t) => (
        <div key={t.id} style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 600 }}>{t.ticker}</span>
          <span style={{ color: '#6b7280', fontSize: 14 }}>Alert at risk score ≥ {t.threshold}</span>
          <button onClick={() => deleteMutation.mutate(t.ticker)}
            style={{ background: 'none', border: '1px solid #ef4444', color: '#ef4444', borderRadius: 4, padding: '3px 10px', cursor: 'pointer', fontSize: 12 }}>
            Delete
          </button>
        </div>
      ))}
    </div>
  )
}
