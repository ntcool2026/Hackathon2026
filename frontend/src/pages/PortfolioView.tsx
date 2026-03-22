import { useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../context/AuthContext'
import { useWebSocket, type PortfolioAnalysis } from '../hooks/useWebSocket'
import { apiFetch } from '../hooks/useApi'
import StockCard from '../components/StockCard'
import PortfolioSummary from '../components/PortfolioSummary'
import ChatPanel from '../components/ChatPanel'

const API = import.meta.env.VITE_API_URL ?? ''

interface StockEntry {
  ticker: string
  added_at: string
  price?: number | null
  price_change_pct?: number | null
  score?: {
    risk_score: number
    recommendation: 'BUY' | 'HOLD' | 'SELL'
    breakdown?: {
      peg_score: number
      beta_score: number
      pe_score: number
      sector_score: number
      final_score: number
    }
    rationale?: string
    ai_risk_score?: number | null
    ai_recommendation?: 'BUY' | 'HOLD' | 'SELL' | null
    is_stale?: boolean
  }
}

async function fetchStocks(portfolioId: string): Promise<StockEntry[]> {
  const res = await apiFetch(`${API}/api/portfolios/${portfolioId}/stocks`)
  if (!res.ok) throw new Error('Failed to fetch stocks')
  return res.json()
}

async function addStock(portfolioId: string, ticker: string): Promise<void> {
  const res = await apiFetch(`${API}/api/portfolios/${portfolioId}/stocks`, {
    method: 'POST',
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
  const res = await apiFetch(`${API}/api/portfolios/${portfolioId}/stocks/${ticker}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('Failed to remove stock')
}

export default function PortfolioView() {
  const { id: portfolioId } = useParams<{ id: string }>()
  const { user } = useAuth()
  const userId = (user?.id as string) ?? null
  const [chatOpen, setChatOpen] = useState(false)
  const [portfolioAnalysis, setPortfolioAnalysis] = useState<PortfolioAnalysis | null>(null)
  const [analysisDismissed, setAnalysisDismissed] = useState(false)

  const handlePortfolioAnalysis = useCallback((data: PortfolioAnalysis) => {
    setPortfolioAnalysis(data)
    setAnalysisDismissed(false)
  }, [])

  useWebSocket(userId, null, handlePortfolioAnalysis)

  const queryClient = useQueryClient()
  const [tickerInput, setTickerInput] = useState('')
  const [addError, setAddError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [showSummary, setShowSummary] = useState(false)

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await apiFetch(`${API}/api/scores/refresh`, { method: 'POST' })
      // Invalidate immediately so quant scores refresh; AI scores arrive via WebSocket
      queryClient.invalidateQueries({ queryKey: ['stocks', portfolioId] })
    } catch {
      // ignore
    } finally {
      // Stop spinner after a short delay — WebSocket will push AI updates as they arrive
      setTimeout(() => setRefreshing(false), 3000)
    }
  }

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

  if (isLoading) return (
    <div className="page-container">
      {[1, 2, 3].map((i) => (
        <div key={i} className="card" style={{ padding: 16, marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ width: 80, height: 20, background: '#e5e7eb', borderRadius: 4, animation: 'pulse 1.5s ease-in-out infinite' }} />
            <div style={{ width: 50, height: 22, background: '#e5e7eb', borderRadius: 999, animation: 'pulse 1.5s ease-in-out infinite' }} />
          </div>
          <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ height: 8, background: '#e5e7eb', borderRadius: 4, animation: 'pulse 1.5s ease-in-out infinite' }} />
            <div style={{ height: 8, background: '#e5e7eb', borderRadius: 4, animation: 'pulse 1.5s ease-in-out infinite' }} />
          </div>
        </div>
      ))}
    </div>
  )

  return (
    <>
    {chatOpen && <ChatPanel onClose={() => setChatOpen(false)} />}
    <div className="page-container">
      <Link to="/dashboard" style={{ fontSize: 13, color: 'var(--color-text-sub)' }}>← Back to portfolios</Link>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>Portfolio Stocks</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {stocks.length > 0 && (
            <button
              className="btn-ghost"
              onClick={() => setShowSummary((v) => !v)}
              style={{ fontSize: 13 }}
            >
              {showSummary ? '▲ Hide summary' : '▼ Summary'}
            </button>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            title={refreshing ? 'Refreshing…' : 'Refresh data'}
            style={{
              background: 'none',
              border: 'none',
              cursor: refreshing ? 'default' : 'pointer',
              fontSize: 22,
              color: refreshing ? 'var(--color-muted)' : 'var(--color-primary)',
              padding: 4,
              lineHeight: 1,
            }}
          >
            <span style={{ display: 'inline-block', animation: refreshing ? 'spin 1s linear infinite' : 'none' }}>↻</span>
          </button>
          <button
            onClick={() => setChatOpen((v) => !v)}
            title="Portfolio Advisor"
            style={{
              background: chatOpen ? 'var(--color-primary)' : 'none',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              fontSize: 18,
              color: chatOpen ? '#0a1118' : 'var(--color-text)',
              padding: '3px 10px',
              lineHeight: 1,
            }}
          >
            💬
          </button>
        </div>
      </div>

      {/* Portfolio analysis banner */}
      {portfolioAnalysis && !analysisDismissed && (
        <div style={{
          background: 'var(--color-bg)',
          border: '1px solid var(--color-border)',
          borderLeft: '4px solid var(--color-primary)',
          borderRadius: 'var(--radius-sm)',
          padding: '10px 14px',
          marginBottom: 16,
          fontSize: 13,
          display: 'flex',
          gap: 10,
          alignItems: 'flex-start',
        }}>
          <span style={{ flex: 1, lineHeight: 1.55, color: 'var(--color-text)' }}>
            <span style={{ fontWeight: 600, marginRight: 6 }}>Portfolio insight:</span>
            {portfolioAnalysis.summary}
            {portfolioAnalysis.concentration_flags.length > 0 && (
              <span style={{ marginLeft: 8, color: 'var(--color-hold)', fontWeight: 600 }}>
                ⚠ Concentration: {portfolioAnalysis.concentration_flags.join(', ')}
              </span>
            )}
          </span>
          <button
            onClick={() => setAnalysisDismissed(true)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-muted)', fontSize: 16, lineHeight: 1, flexShrink: 0 }}
          >
            ×
          </button>
        </div>
      )}

      <form onSubmit={handleAdd} style={{ position: 'relative', maxWidth: 320, marginBottom: 20 }}>
        <input
          value={tickerInput}
          onChange={(e) => setTickerInput(e.target.value.toUpperCase())}
          placeholder="Add ticker (e.g. AAPL)"
          style={{
            width: '100%',
            padding: '7px 36px 7px 12px',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-sm)',
            fontSize: 13,
            outline: 'none',
            background: 'var(--color-surface)',
            color: 'var(--color-text)',
            transition: 'border-color 0.15s',
          }}
          onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--color-primary)')}
          onBlur={(e) => (e.currentTarget.style.borderColor = 'var(--color-border)')}
        />
        <button
          type="submit"
          disabled={addMutation.isPending}
          title="Add ticker"
          style={{
            position: 'absolute',
            right: 4,
            top: '50%',
            transform: 'translateY(-50%)',
            background: 'none',
            border: 'none',
            cursor: addMutation.isPending ? 'default' : 'pointer',
            color: tickerInput ? 'var(--color-primary)' : 'var(--color-muted)',
            fontSize: 18,
            lineHeight: 1,
            padding: '2px 4px',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          {addMutation.isPending ? '…' : '+'}
        </button>
      </form>
      {addError && <p style={{ color: 'var(--color-sell)', fontSize: 13, marginBottom: 12 }}>{addError}</p>}

      {showSummary && stocks.length > 0 && <PortfolioSummary stocks={stocks} />}

      {stocks.length === 0 && (
        <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--color-text-sub)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📊</div>
          <p>No stocks yet. Add a ticker above.</p>
        </div>
      )}

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
        gap: 12,
      }}>
        {stocks.map((s) => (
          <StockCard
            key={s.ticker}
            ticker={s.ticker}
            price={s.price}
            priceChangePct={s.price_change_pct}
            riskScore={s.score?.risk_score ?? 0}
            recommendation={s.score?.recommendation ?? 'HOLD'}
            aiRecommendation={s.score?.ai_recommendation}
            breakdown={s.score?.breakdown}
            rationale={s.score?.rationale}
            aiRiskScore={s.score?.ai_risk_score}
            isStale={s.score?.is_stale}
            onRemove={() => removeMutation.mutate(s.ticker)}
          />
        ))}
      </div>
    </div>
    </>
  )
}
