import { useState } from 'react'

interface Breakdown {
  volatility_score: number
  beta_score: number
  dte_score: number
  sector_score: number
  final_score: number
}

interface StockCardProps {
  ticker: string
  riskScore: number
  recommendation: 'BUY' | 'HOLD' | 'SELL'
  breakdown?: Breakdown | null
  rationale?: string | null
  isStale?: boolean
}

function scoreColor(score: number): string {
  if (score < 35) return '#22c55e'   // green — BUY
  if (score < 65) return '#eab308'   // yellow — HOLD
  return '#ef4444'                    // red — SELL
}

function recBadgeStyle(rec: string): React.CSSProperties {
  const colors: Record<string, string> = {
    BUY: '#22c55e',
    HOLD: '#eab308',
    SELL: '#ef4444',
  }
  return {
    background: colors[rec] ?? '#6b7280',
    color: '#fff',
    padding: '2px 10px',
    borderRadius: 4,
    fontWeight: 700,
    fontSize: 13,
  }
}

export default function StockCard({
  ticker,
  riskScore,
  recommendation,
  breakdown,
  rationale,
  isStale,
}: StockCardProps) {
  const [showRationale, setShowRationale] = useState(false)

  const components = breakdown
    ? [
        { label: 'Volatility', value: breakdown.volatility_score },
        { label: 'Beta', value: breakdown.beta_score },
        { label: 'Debt/Equity', value: breakdown.dte_score },
        { label: 'Sector', value: breakdown.sector_score },
      ]
    : []

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 700, fontSize: 18 }}>
          {ticker}
          {isStale && (
            <span style={{ marginLeft: 8, fontSize: 11, color: '#9ca3af' }}>⚠ stale</span>
          )}
        </span>
        <span style={recBadgeStyle(recommendation)}>{recommendation}</span>
      </div>

      {/* Risk score gauge */}
      <div style={{ marginTop: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#6b7280' }}>
          <span>Risk Score</span>
          <span style={{ fontWeight: 700, color: scoreColor(riskScore) }}>
            {riskScore.toFixed(1)}
          </span>
        </div>
        <div style={{ background: '#e5e7eb', borderRadius: 4, height: 8, marginTop: 4 }}>
          <div
            style={{
              width: `${riskScore}%`,
              background: scoreColor(riskScore),
              height: '100%',
              borderRadius: 4,
              transition: 'width 0.4s',
            }}
          />
        </div>
      </div>

      {/* Breakdown bars */}
      {components.length > 0 && (
        <div style={{ marginTop: 10 }}>
          {components.map(({ label, value }) => (
            <div key={label} style={{ marginBottom: 4 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#6b7280' }}>
                <span>{label}</span>
                <span>{value.toFixed(1)}</span>
              </div>
              <div style={{ background: '#e5e7eb', borderRadius: 2, height: 4 }}>
                <div
                  style={{
                    width: `${value}%`,
                    background: '#6366f1',
                    height: '100%',
                    borderRadius: 2,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Rationale */}
      <div style={{ marginTop: 10 }}>
        <button
          onClick={() => setShowRationale((v) => !v)}
          style={{ fontSize: 12, color: '#6366f1', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
        >
          {showRationale ? 'Hide rationale ▲' : 'Show rationale ▼'}
        </button>
        {showRationale && (
          <p style={{ marginTop: 6, fontSize: 13, color: '#374151', lineHeight: 1.5 }}>
            {rationale ?? 'Rationale loading…'}
          </p>
        )}
      </div>
    </div>
  )
}
