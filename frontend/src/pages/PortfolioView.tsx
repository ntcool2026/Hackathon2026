import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../context/AuthContext'
import { useWebSocket } from '../hooks/useWebSocket'
import StockCard from '../components/StockCard'

const API = import.meta.env.VITE_API_URL ?? ''

interface StockEntry {
  ticker: string
  added_at: string
  score?: {
    risk_score: number
    recommendation: 'BUY' | 'HOLD' | 'SELL'
    breakdown?: {
      volatility_score: number
      beta_score: number
      dte_score: number
      sector_score: number
      final_score: number
    }
    rationale?: string
    is_stale?: boolean
  }
}

async function fetchStocks(portfolioId: string): Promise<StockEntry[]> {
  const res = await fetch(`${API}/api/portfolios/${portfolioId}/stocks`, { credentials: 'include' })
  if (!res.ok) throw new Error('Failed to fetch stocks')
  return res.json()
}

async function addStock(portfolioId: string, ticker: string): Promise<void> {
  const res = await fetch(`${API}/api/portfolios/${portfolioId}/stocks`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticker }),
  })
  if (res.status === 422) {
    const data = await res.json()
    throw new Error(data.detail ?? 'Invalid ticker')
  }
  if (!res.ok) throw new Error('Failed to add stock')
}

async function removeStock(portfolioId: string, ticker: string): Promise<void> {
  const res = await fetch(`${API}/api/portfolios/${portfolioId}/stocks/${ticker}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) throw new Error('Failed to remove stock')
}

export default function PortfolioView() {
  const { id: portfolioId } = useParams<{ id: string }>()
  const { userId, token } = useAuth()
  useWebSocket(userId, token)

  const queryClient = useQueryClient()
  const [tickerInput, setTickerInput] = useState('')
  const [addError, setAddError] = useState<string | null>(null)

  const { data: stocks = [], isLoading } = useQuery({
    queryKey: ['stocks', portfolioId],
    queryFn: () => fetchStocks(portfolioId!),
    enabled: !!portfolioId,
  })

  const addMutation = useMutation({
    mutationFn: (ticker: string) => addStock(portfolioId!, ticker),
    onSuccess: () => {
      setTickerInput('')
      setAddError(null)
      queryClient.invalidateQueries({ queryKey: ['stocks', portfolioId] })
    },
    onError: (err: Error) => setAddError(err.message),
  })

  const removeMutation = useMutation({
    mutationFn: (ticker: string) => removeStock(portfolioId!, ticker),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['stocks', portfolioId] }),
  })

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault()
    const t = tickerInput.trim().toUpperCase()
    if (!t) return
    setAddError(null)
    addMutation.mutate(t)
  }

  if (isLoading) return <p style={{ padding: 24 }}>Loading…</p>

  return (
    <div style={{ maxWidth: 700, margin: '0 auto', padding: 24 }}>
      <Link to="/dashboard" style={{ color: '#6366f1', fontSize: 14 }}>← Back to portfolios</Link>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginTop: 12, marginBottom: 16 }}>Portfolio Stocks</h1>

      <form onSubmit={handleAdd} style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <input
          value={tickerInput}
          onChange={(e) => setTickerInput(e.target.value.toUpperCase())}
          placeholder="Ticker (e.g. AAPL)"
          style={{ flex: 1, padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14 }}
        />
        <button
          type="submit"
          disabled={addMutation.isPending}
          style={{ background: '#6366f1', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 18px', cursor: 'pointer' }}
        >
          {addMutation.isPending ? 'Adding…' : 'Add'}
        </button>
      </form>
      {addError && <p style={{ color: '#ef4444', fontSize: 13, marginBottom: 12 }}>{addError}</p>}

      {stocks.length === 0 && <p style={{ color: '#6b7280' }}>No stocks yet. Add a ticker above.</p>}

      {stocks.map((s) => (
        <div key={s.ticker} style={{ position: 'relative' }}>
          <StockCard
            ticker={s.ticker}
            riskScore={s.score?.risk_score ?? 0}
            recommendation={s.score?.recommendation ?? 'HOLD'}
            breakdown={s.score?.breakdown}
            rationale={s.score?.rationale}
            isStale={s.score?.is_stale}
          />
          <button
            onClick={() => removeMutation.mutate(s.ticker)}
            style={{
              position: 'absolute',
              top: 16,
              right: 16,
              background: 'none',
              border: '1px solid #ef4444',
              color: '#ef4444',
              borderRadius: 4,
              padding: '2px 10px',
              cursor: 'pointer',
              fontSize: 12,
            }}
          >
            Remove
          </button>
        </div>
      ))}
    </div>
  )
}
