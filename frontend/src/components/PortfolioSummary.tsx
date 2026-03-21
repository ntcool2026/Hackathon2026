import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts'
import { apiFetch } from '../hooks/useApi'

const API = import.meta.env.VITE_API_URL ?? ''

interface StockEntry {
  ticker: string
  score?: {
    recommendation: 'BUY' | 'HOLD' | 'SELL'
    ai_recommendation?: 'BUY' | 'HOLD' | 'SELL' | null
    risk_score: number
    ai_risk_score?: number | null
  }
}

interface PortfolioSummaryProps {
  stocks: StockEntry[]
}

const REC_COLOR: Record<string, string> = {
  BUY: 'var(--color-buy)',
  HOLD: 'var(--color-hold)',
  SELL: 'var(--color-sell)',
}

// 10 distinct line colours for the combined chart
const LINE_COLORS = [
  '#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4',
  '#a855f7', '#ec4899', '#84cc16', '#f97316', '#14b8a6',
]

function recBadge(rec: string) {
  return (
    <span style={{
      background: REC_COLOR[rec] ?? 'var(--color-muted)',
      color: '#fff',
      padding: '2px 10px',
      borderRadius: 'var(--radius-pill)',
      fontWeight: 700,
      fontSize: 11,
      letterSpacing: '0.4px',
    }}>
      {rec}
    </span>
  )
}

function scoreBar(score: number | null | undefined) {
  if (score == null) return <span style={{ color: 'var(--color-muted)', fontSize: 12 }}>—</span>
  const color = score < 35 ? 'var(--color-buy)' : score < 65 ? 'var(--color-hold)' : 'var(--color-sell)'
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ fontSize: 12, fontWeight: 700, color }}>{score.toFixed(1)}</span>
      <span style={{ flex: 1, minWidth: 60, height: 6, background: 'var(--color-border)', borderRadius: 3, display: 'inline-block' }}>
        <span style={{ display: 'block', width: `${score}%`, height: '100%', background: color, borderRadius: 3 }} />
      </span>
    </span>
  )
}

type Period = '1w' | '1y' | '2y'

function CombinedChart({ tickers }: { tickers: string[] }) {
  const [period, setPeriod] = useState<Period>('1y')
  const tickerParam = tickers.join(',')

  const { data, isLoading } = useQuery({
    queryKey: ['multi-price-history', tickerParam, period],
    queryFn: async () => {
      const res = await apiFetch(`${API}/api/scores/price-history/multi?tickers=${encodeURIComponent(tickerParam)}&period=${period}`)
      if (!res.ok) throw new Error('Failed')
      return res.json() as Promise<{ period: string; series: Record<string, { date: string; pct: number }[]> }>
    },
    enabled: tickers.length > 0,
    staleTime: 5 * 60 * 1000,
  })

  const periodButtons = (
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
  )

  if (isLoading) return <>{periodButtons}<p style={{ fontSize: 12, color: 'var(--color-muted)', padding: '4px 0' }}>Loading chart…</p></>
  if (!data) return null

  const dateMap: Record<string, Record<string, number>> = {}
  for (const [ticker, points] of Object.entries(data.series)) {
    for (const p of points) {
      if (!dateMap[p.date]) dateMap[p.date] = {}
      dateMap[p.date][ticker] = p.pct
    }
  }
  const chartData = Object.entries(dateMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, vals]) => ({ date, ...vals }))

  const step = Math.max(1, Math.floor(chartData.length / 8))
  const xTicks = chartData.filter((_, i) => i % step === 0).map((p) => p.date)

  return (
    <>
      {periodButtons}
      <ResponsiveContainer width="100%" height={260}>
      <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <XAxis dataKey="date" ticks={xTicks} tick={{ fontSize: 10, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
        <YAxis
          tick={{ fontSize: 10, fill: '#9ca3af' }}
          tickLine={false}
          axisLine={false}
          width={44}
          tickFormatter={(v) => `${v > 0 ? '+' : ''}${v.toFixed(0)}%`}
        />
        <ReferenceLine y={0} stroke="#e5e7eb" strokeDasharray="3 3" />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 6, border: '1px solid #e5e7eb' }}
          formatter={(v: unknown, name: unknown) => [`${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(2)}%`, String(name)]}
          labelStyle={{ color: '#6b7280' }}
        />
        <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
        {tickers.map((ticker, i) => (
          <Line
            key={ticker}
            type="monotone"
            dataKey={ticker}
            stroke={LINE_COLORS[i % LINE_COLORS.length]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
    </>
  )
}

export default function PortfolioSummary({ stocks }: PortfolioSummaryProps) {
  const tickers = stocks.map((s) => s.ticker)

  const byRec: Record<string, StockEntry[]> = { BUY: [], HOLD: [], SELL: [] }
  for (const s of stocks) {
    const rec = s.score?.recommendation ?? 'HOLD'
    byRec[rec].push(s)
  }

  return (
    <div style={{ marginBottom: 24 }}>
      {/* Recommendation table */}
      <div className="card" style={{ padding: '14px 16px', marginBottom: 16 }}>
        <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text)', marginBottom: 12 }}>
          Portfolio Summary
        </p>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ color: 'var(--color-text-sub)', fontSize: 11 }}>
              <th style={{ textAlign: 'left', paddingBottom: 6, fontWeight: 600 }}>Ticker</th>
              <th style={{ textAlign: 'left', paddingBottom: 6, fontWeight: 600 }}>Quant</th>
              <th style={{ textAlign: 'left', paddingBottom: 6, fontWeight: 600 }}>AI Signal</th>
              <th style={{ textAlign: 'left', paddingBottom: 6, fontWeight: 600 }}>Quant Score</th>
              <th style={{ textAlign: 'left', paddingBottom: 6, fontWeight: 600 }}>AI Score</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((s) => {
              const qRec = s.score?.recommendation ?? 'HOLD'
              const aiRec = s.score?.ai_recommendation
              const conflict = aiRec && aiRec !== qRec
              return (
                <tr key={s.ticker} style={{ borderTop: '1px solid var(--color-border)' }}>
                  <td style={{ padding: '7px 0', fontWeight: 700, color: 'var(--color-text)' }}>{s.ticker}</td>
                  <td style={{ padding: '7px 8px 7px 0' }}>{recBadge(qRec)}</td>
                  <td style={{ padding: '7px 8px 7px 0' }}>
                    {aiRec
                      ? <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          {recBadge(aiRec)}
                          {conflict && <span title="Differs from quant" style={{ fontSize: 11, color: 'var(--color-hold)' }}>⚠</span>}
                          {!conflict && <span style={{ fontSize: 10, color: 'var(--color-buy)' }}>✓</span>}
                        </span>
                      : <span style={{ color: 'var(--color-muted)', fontSize: 12 }}>pending</span>
                    }
                  </td>
                  <td style={{ padding: '7px 8px 7px 0', minWidth: 120 }}>{scoreBar(s.score?.risk_score)}</td>
                  <td style={{ padding: '7px 0', minWidth: 120 }}>{scoreBar(s.score?.ai_risk_score)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Combined 2y chart */}
      {tickers.length > 0 && (
        <div className="card" style={{ padding: '14px 16px' }}>
          <p style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text)', marginBottom: 4 }}>
            Performance (% change)
          </p>
          <p style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 12 }}>
            Normalised to each ticker's starting price
          </p>
          <CombinedChart tickers={tickers} />
        </div>
      )}
    </div>
  )
}
