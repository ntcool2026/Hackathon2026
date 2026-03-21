import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

const API = import.meta.env.VITE_API_URL ?? ''

interface Prefs {
  risk_tolerance: number
  time_horizon: string
  sector_preference: string[]
  dividend_preference: boolean
  growth_vs_value: string
}

interface PreviewScore {
  ticker: string
  risk_score: number
  recommendation: string
}

async function fetchPrefs(): Promise<Prefs> {
  const res = await fetch(`${API}/api/preferences`, { credentials: 'include' })
  if (!res.ok) throw new Error('Failed to fetch preferences')
  return res.json()
}

async function savePrefs(prefs: Prefs): Promise<void> {
  const res = await fetch(`${API}/api/preferences`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(prefs),
  })
  if (!res.ok) throw new Error('Failed to save preferences')
}

async function fetchPreview(prefs: Prefs): Promise<PreviewScore[]> {
  const params = new URLSearchParams({
    risk_tolerance: String(prefs.risk_tolerance),
    time_horizon: prefs.time_horizon,
    sector_preference: prefs.sector_preference.join(','),
    dividend_preference: String(prefs.dividend_preference),
    growth_vs_value: prefs.growth_vs_value,
  })
  const res = await fetch(`${API}/api/preferences/preview?${params}`, { credentials: 'include' })
  if (!res.ok) throw new Error('Failed to fetch preview')
  const data = await res.json()
  return data.previews ?? []
}

const DEFAULT_PREFS: Prefs = {
  risk_tolerance: 5,
  time_horizon: 'medium',
  sector_preference: [],
  dividend_preference: false,
  growth_vs_value: 'balanced',
}

export default function PreferencesForm() {
  const queryClient = useQueryClient()
  const { data: saved } = useQuery({ queryKey: ['preferences'], queryFn: fetchPrefs })
  const [prefs, setPrefs] = useState<Prefs>(DEFAULT_PREFS)
  const [preview, setPreview] = useState<PreviewScore[]>([])
  const [previewLoading, setPreviewLoading] = useState(false)

  useEffect(() => {
    if (saved) setPrefs(saved)
  }, [saved])

  const saveMutation = useMutation({
    mutationFn: savePrefs,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['preferences'] }),
  })

  const handleChange = async (updated: Prefs) => {
    setPrefs(updated)
    setPreviewLoading(true)
    try {
      const scores = await fetchPreview(updated)
      setPreview(scores)
    } catch {
      // ignore preview errors
    } finally {
      setPreviewLoading(false)
    }
  }

  const set = (key: keyof Prefs, value: unknown) =>
    handleChange({ ...prefs, [key]: value })

  return (
    <div style={{ maxWidth: 600, margin: '0 auto', padding: 24 }}>
      <Link to="/dashboard" style={{ color: '#6366f1', fontSize: 14 }}>← Back</Link>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginTop: 12, marginBottom: 20 }}>Preferences</h1>

      <label style={labelStyle}>
        Risk Tolerance: {prefs.risk_tolerance}
        <input
          type="range" min={1} max={10} value={prefs.risk_tolerance}
          onChange={(e) => set('risk_tolerance', Number(e.target.value))}
          style={{ width: '100%', marginTop: 4 }}
        />
      </label>

      <label style={labelStyle}>
        Time Horizon
        <select value={prefs.time_horizon} onChange={(e) => set('time_horizon', e.target.value)} style={selectStyle}>
          <option value="short">Short</option>
          <option value="medium">Medium</option>
          <option value="long">Long</option>
        </select>
      </label>

      <label style={labelStyle}>
        Growth vs Value
        <select value={prefs.growth_vs_value} onChange={(e) => set('growth_vs_value', e.target.value)} style={selectStyle}>
          <option value="growth">Growth</option>
          <option value="balanced">Balanced</option>
          <option value="value">Value</option>
        </select>
      </label>

      <label style={{ ...labelStyle, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <input
          type="checkbox"
          checked={prefs.dividend_preference}
          onChange={(e) => set('dividend_preference', e.target.checked)}
        />
        Prefer dividend stocks
      </label>

      <button
        onClick={() => saveMutation.mutate(prefs)}
        disabled={saveMutation.isPending}
        style={{ marginTop: 20, background: '#6366f1', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 24px', cursor: 'pointer', fontWeight: 600 }}
      >
        {saveMutation.isPending ? 'Saving…' : 'Save Preferences'}
      </button>

      {/* Live preview */}
      {preview.length > 0 && (
        <div style={{ marginTop: 28 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>
            Live Preview {previewLoading && <span style={{ fontSize: 12, color: '#9ca3af' }}>updating…</span>}
          </h2>
          {preview.map((s) => (
            <div key={s.ticker} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f3f4f6', fontSize: 14 }}>
              <span style={{ fontWeight: 600 }}>{s.ticker}</span>
              <span>{s.risk_score.toFixed(1)}</span>
              <span style={{ color: s.recommendation === 'BUY' ? '#22c55e' : s.recommendation === 'SELL' ? '#ef4444' : '#eab308', fontWeight: 700 }}>
                {s.recommendation}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const labelStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  marginBottom: 16,
  fontSize: 14,
  fontWeight: 500,
  color: '#374151',
}

const selectStyle: React.CSSProperties = {
  marginTop: 4,
  padding: '6px 10px',
  border: '1px solid #d1d5db',
  borderRadius: 6,
  fontSize: 14,
}
