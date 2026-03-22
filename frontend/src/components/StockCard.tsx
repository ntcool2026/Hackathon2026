import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts'
import { apiFetch } from '../hooks/useApi'

const API = import.meta.env.VITE_API_URL ?? ''

interface Breakdown {
  peg_score: number
  beta_score: number
  pe_score: number
  sector_score: number
  final_score: number
}

interface StockCardProps {
  ticker: string
  price?: number | null
  priceChangePct?: number | null
  riskScore: number
  recommendation: 'BUY' | 'HOLD' | 'SELL'
  aiRecommendation?: 'BUY' | 'HOLD' | 'SELL' | null
  breakdown?: Breakdown | null
  rationale?: string | null
  aiRiskScore?: number | null
  isStale?: boolean
  onRemove?: () => void
}

type Period = '1w' | '1y' | '2y'

// Metric metadata: description and direction hint
const METRIC_META: Record<string, { desc: string; hint: string }> = {
  'PEG Ratio': {
    desc: 'Price/Earnings-to-Growth — compares valuation to earnings growth rate.',
    hint: 'Lower is better',
  },
  'Beta': {
    desc: 'Measures price volatility relative to the market (1.0 = market average).',
    hint: 'Lower is better',
  },
  'P/E Ratio': {
    desc: 'Price-to-Earnings — how much investors pay per dollar of earnings.',
    hint: 'Lower is better',
  },
  'Sector': {
    desc: 'Risk level inherent to the stock\'s industry sector.',
    hint: 'Lower is better',
  },
}

function scoreColor(score: number): string {
  if (score < 35) return 'var(--color-buy)'
  if (score < 65) return 'var(--color-hold)'
  return 'var(--color-sell)'
}

function recBadgeStyle(rec: string): CSSProperties {
  const colors: Record<string, string> = {
    BUY:  'var(--color-buy)',
    HOLD: 'var(--color-hold)',
    SELL: 'var(--color-sell)',
  }
  return {
    background: colors[rec] ?? 'var(--color-muted)',
    color: '#fff',
    padding: '3px 12px',
    borderRadius: 'var(--radius-pill)',
    fontWeight: 700,
    fontSize: 12,
    letterSpacing: '0.5px',
  }
}

function recBorderColor(rec: string): string {
  const colors: Record<string, string> = {
    BUY:  'var(--color-buy)',
    HOLD: 'var(--color-hold)',
    SELL: 'var(--color-sell)',
  }
  return colors[rec] ?? 'var(--color-border)'
}

function Tooltip2({ text }: { text: string }) {
  const [visible, setVisible] = useState(false)
  return (
    <span style={{ position: 'relative', display: 'inline-block', marginLeft: 4 }}>
      <span
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        style={{ cursor: 'help', color: '#9ca3af', fontSize: 11, userSelect: 'none' }}
      >
        ⓘ
      </span>
      {visible && (
        <span style={{
          position: 'absolute',
          bottom: '120%',
          left: '50%',
          transform: 'translateX(-50%)',
          background: '#1f2937',
          color: '#f9fafb',
          fontSize: 11,
          padding: '5px 8px',
          borderRadius: 5,
          zIndex: 10,
          pointerEvents: 'none',
          maxWidth: 220,
          whiteSpace: 'normal',
          lineHeight: 1.4,
        }}>
          {text}
        </span>
      )}
    </span>
  )
}

function PriceChart({ ticker }: { ticker: string }) {
  const [period, setPeriod] = useState<Period>('1y')

  const { data, isLoading } = useQuery({
    queryKey: ['price-history', ticker, period],
    queryFn: async () => {
      const res = await apiFetch(`${API}/api/scores/${ticker}/price-history?period=${period}`)
      if (!res.ok) throw new Error('Failed to fetch price history')
      return res.json() as Promise<{ data: { date: string; close: number }[] }>
    },
    staleTime: 5 * 60 * 1000,
  })

  const points = data?.data ?? []
  const minVal = points.length ? Math.min(...points.map((p) => p.close)) : 0
  const maxVal = points.length ? Math.max(...points.map((p) => p.close)) : 0
  const domainPad = (maxVal - minVal) * 0.05 || 1
  const tickCount = period === '1w' ? 7 : 6
  const step = Math.max(1, Math.floor(points.length / tickCount))
  const ticks = points.filter((_, i) => i % step === 0).map((p) => p.date)

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
        {(['1w', '1y', '2y'] as Period[]).map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            style={{
              fontSize: 11,
              padding: '2px 10px',
              borderRadius: 4,
              border: '1px solid var(--color-border)',
              background: period === p ? 'var(--color-primary)' : 'var(--color-surface)',
              color: period === p ? '#0a1118' : 'var(--color-text-sub)',
              cursor: 'pointer',
              fontWeight: period === p ? 700 : 400,
            }}
          >
            {p}
          </button>
        ))}
      </div>
      {isLoading && <p style={{ fontSize: 12, color: 'var(--color-muted)' }}>Loading chart…</p>}
      {!isLoading && points.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--color-muted)' }}>No price data available.</p>
      )}
      {!isLoading && points.length > 0 && (
        <ResponsiveContainer width="100%" height={140}>
          <AreaChart data={points} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`grad-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="date" ticks={ticks} tick={{ fontSize: 10, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
            <YAxis
              domain={[minVal - domainPad, maxVal + domainPad]}
              tick={{ fontSize: 10, fill: '#9ca3af' }}
              tickLine={false}
              axisLine={false}
              width={48}
              tickFormatter={(v) => `${v.toFixed(0)}`}
            />
            <Tooltip
              contentStyle={{ fontSize: 12, borderRadius: 6, border: '1px solid #e5e7eb' }}
              formatter={((v: unknown) => [`${Number(v).toFixed(2)}`, 'Close']) as never}
              labelStyle={{ color: '#6b7280' }}
            />
            <Area type="monotone" dataKey="close" stroke="#6366f1" strokeWidth={2} fill={`url(#grad-${ticker})`} dot={false} activeDot={{ r: 4 }} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

export default function StockCard({
  ticker,
  price,
  priceChangePct,
  riskScore,
  recommendation,
  aiRecommendation,
  breakdown,
  rationale,
  aiRiskScore,
  isStale,
  onRemove,
}: StockCardProps) {
  const [showRationale, setShowRationale] = useState(false)
  const [showChart, setShowChart] = useState(false)

  const components = breakdown
    ? [
        { label: 'PEG Ratio', value: breakdown.peg_score },
        { label: 'Beta', value: breakdown.beta_score },
        { label: 'P/E Ratio', value: breakdown.pe_score },
        { label: 'Sector', value: breakdown.sector_score },
      ]
    : []

  return (
    <div
      className="card"
      style={{
        padding: 16,
        borderLeft: `4px solid ${recBorderColor(recommendation)}`,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', minWidth: 0 }}>
          <span style={{ fontWeight: 700, fontSize: 18, color: 'var(--color-text)' }}>{ticker}</span>
          {isStale && <span style={{ fontSize: 11, color: 'var(--color-muted)' }}>⚠ stale</span>}
          {price != null && (
            <span style={{ fontSize: 14, color: 'var(--color-text-sub)', fontWeight: 600 }}>
              ${price.toFixed(2)}
              {priceChangePct != null && (
                <span style={{
                  marginLeft: 6,
                  fontSize: 12,
                  fontWeight: 600,
                  color: priceChangePct >= 0 ? 'var(--color-buy)' : 'var(--color-sell)',
                }}>
                  {priceChangePct >= 0 ? '+' : ''}{priceChangePct.toFixed(2)}%
                </span>
              )}
            </span>
          )}
        </div>
        {/* Delete + Quant/AI badges — stacked vertically on the right */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
          {onRemove && (
            <button
              onClick={onRemove}
              title="Remove from portfolio"
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--color-muted)',
                cursor: 'pointer',
                fontSize: 18,
                lineHeight: 1,
                padding: '0 2px',
              }}
            >
              ×
            </button>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ fontSize: 10, color: 'var(--color-muted)' }}>Quant</span>
            <span style={recBadgeStyle(recommendation)}>{recommendation}</span>
          </div>
          {aiRecommendation && aiRecommendation !== recommendation ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ fontSize: 10, color: 'var(--color-muted)' }}>AI</span>
              <span style={{ ...recBadgeStyle(aiRecommendation), opacity: 0.9 }}>{aiRecommendation}</span>
            </div>
          ) : aiRecommendation ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ fontSize: 10, color: 'var(--color-muted)' }}>AI ✓</span>
            </div>
          ) : null}
        </div>
      </div>

      {/* Dual risk scores — stacked */}
      <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* Quantitative score */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--color-text-sub)', marginBottom: 4 }}>
            <span>
              Quant Risk Score
              <Tooltip2 text="Deterministic score computed from PEG ratio, Beta, P/E ratio, and sector weights. Lower = less risk." />
            </span>
            <span style={{ fontWeight: 700, color: scoreColor(riskScore) }}>{riskScore.toFixed(1)}</span>
          </div>
          <div style={{ background: 'var(--color-border)', borderRadius: 4, height: 8 }}>
            <div style={{ width: `${riskScore}%`, background: scoreColor(riskScore), height: '100%', borderRadius: 4, transition: 'width 0.4s' }} />
          </div>
        </div>

        {/* AI score */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--color-text-sub)', marginBottom: 4 }}>
            <span>
              AI Risk Score
              <Tooltip2 text="AI-assessed risk based on news sentiment, earnings surprises, and SEC filings. Lower = less risk." />
            </span>
            <span style={{ fontWeight: 700, color: aiRiskScore != null ? scoreColor(aiRiskScore) : 'var(--color-muted)' }}>
              {aiRiskScore != null ? aiRiskScore.toFixed(1) : '—'}
            </span>
          </div>
          <div style={{ background: 'var(--color-border)', borderRadius: 4, height: 8 }}>
            <div style={{
              width: aiRiskScore != null ? `${aiRiskScore}%` : '0%',
              background: aiRiskScore != null ? scoreColor(aiRiskScore) : 'var(--color-muted)',
              height: '100%',
              borderRadius: 4,
              transition: 'width 0.4s',
            }} />
          </div>
        </div>
      </div>

      {/* Breakdown bars */}
      {components.length > 0 && (
        <div style={{ marginTop: 14, background: 'var(--color-bg)', borderRadius: 'var(--radius-sm)', padding: '10px 12px' }}>
          {components.map(({ label, value }) => {
            const meta = METRIC_META[label]
            return (
              <div key={label} style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--color-text-sub)', marginBottom: 3 }}>
                  <span>
                    {label}
                    {meta && <Tooltip2 text={`${meta.desc} ${meta.hint}.`} />}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    {meta && (
                      <span style={{ fontSize: 10, color: 'var(--color-muted)', fontStyle: 'italic' }}>
                        {meta.hint}
                      </span>
                    )}
                    {(value ?? 0).toFixed(1)}
                  </span>
                </div>
                <div style={{ background: 'var(--color-border)', borderRadius: 3, height: 6 }}>
                  <div style={{ width: `${value ?? 0}%`, background: 'var(--color-primary)', height: '100%', borderRadius: 3 }} />
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Chart + Rationale toggles */}
      <div style={{ marginTop: 12, display: 'flex', gap: 16, borderTop: '1px solid var(--color-border)', paddingTop: 10 }}>
        <button className="btn-ghost" onClick={() => setShowChart((v) => !v)}>
          {showChart ? '▲ Hide chart' : '▼ Show chart'}
        </button>
        <button className="btn-ghost" onClick={() => setShowRationale((v) => !v)}>
          {showRationale ? '▲ Hide AI analysis' : '▼ Show AI analysis'}
        </button>
      </div>

      {showChart && <PriceChart ticker={ticker} />}

      {showRationale && (
        <p style={{ marginTop: 10, fontSize: 13, color: 'var(--color-text-sub)', lineHeight: 1.6, background: 'var(--color-bg)', borderRadius: 'var(--radius-sm)', padding: '10px 12px' }}>
          {rationale ?? 'AI analysis loading…'}
        </p>
      )}
    </div>
  )
}
