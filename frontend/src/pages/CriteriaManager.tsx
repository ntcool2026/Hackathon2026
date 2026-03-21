import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { apiFetch } from '../hooks/useApi'

const API = import.meta.env.VITE_API_URL ?? ''

interface Criterion {
  id: string
  name: string
  description?: string
  weight: number
  metric: string
  operator: string
  threshold: string
}

interface CriterionForm {
  name: string
  weight: number
  metric: string
  operator: string
  threshold: string
  description: string
}

const EMPTY_FORM: CriterionForm = { name: '', weight: 5, metric: 'pe_ratio', operator: 'gt', threshold: '0', description: '' }

async function fetchCriteria(): Promise<Criterion[]> {
  const res = await apiFetch(`${API}/api/criteria`)
  if (!res.ok) throw new Error('Failed to fetch criteria')
  return res.json()
}

async function createCriterion(form: CriterionForm): Promise<Criterion> {
  const res = await apiFetch(`${API}/api/criteria`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...form, threshold: Number(form.threshold) }),
  })
  if (!res.ok) {
    const data = await res.json()
    throw new Error(data.detail ?? 'Failed to create criterion')
  }
  return res.json()
}

async function deleteCriterion(id: string): Promise<void> {
  const res = await apiFetch(`${API}/api/criteria/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete criterion')
}

export default function CriteriaManager() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<CriterionForm>(EMPTY_FORM)
  const [formError, setFormError] = useState<string | null>(null)

  const { data: criteria = [] } = useQuery({ queryKey: ['criteria'], queryFn: fetchCriteria })

  const createMutation = useMutation({
    mutationFn: createCriterion,
    onSuccess: () => {
      setForm(EMPTY_FORM)
      setFormError(null)
      queryClient.invalidateQueries({ queryKey: ['criteria'] })
    },
    onError: (err: Error) => setFormError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteCriterion,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['criteria'] }),
  })

  const validate = (): string | null => {
    if (!form.name.trim()) return 'Name is required'
    if (form.weight < 1 || form.weight > 10) return 'Weight must be 1–10'
    if (!form.metric.trim()) return 'Metric is required'
    return null
  }

  const handleSubmit = (e: { preventDefault: () => void }) => {
    e.preventDefault()
    const err = validate()
    if (err) { setFormError(err); return }
    createMutation.mutate(form)
  }

  return (
    <div style={{ maxWidth: 700, margin: '0 auto', padding: 24 }}>
      <Link to="/dashboard" style={{ color: 'var(--color-primary)', fontSize: 14 }}>← Back</Link>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginTop: 12, marginBottom: 20 }}>Custom Criteria</h1>

      <form onSubmit={handleSubmit} style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 8, padding: 16, marginBottom: 24 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <input placeholder="Name *" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={inputStyle} />
          <input type="number" placeholder="Weight (1–10)" min={1} max={10} value={form.weight}
            onChange={(e) => setForm({ ...form, weight: Number(e.target.value) })} style={inputStyle} />
          <input placeholder="Metric (e.g. pe_ratio)" value={form.metric} onChange={(e) => setForm({ ...form, metric: e.target.value })} style={inputStyle} />
          <select value={form.operator} onChange={(e) => setForm({ ...form, operator: e.target.value })} style={inputStyle}>
            <option value="gt">&gt;</option>
            <option value="lt">&lt;</option>
            <option value="gte">&ge;</option>
            <option value="lte">&le;</option>
            <option value="eq">=</option>
          </select>
          <input placeholder="Threshold" value={form.threshold} onChange={(e) => setForm({ ...form, threshold: e.target.value })} style={inputStyle} />
          <input placeholder="Description (optional)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} style={inputStyle} />
        </div>
        {formError && <p style={{ color: 'var(--color-sell)', fontSize: 13, marginTop: 8 }}>{formError}</p>}
        <button type="submit" disabled={createMutation.isPending}
          style={{ marginTop: 12, background: 'var(--color-primary)', color: '#0a1118', border: 'none', borderRadius: 6, padding: '8px 20px', cursor: 'pointer' }}>
          {createMutation.isPending ? 'Adding…' : 'Add Criterion'}
        </button>
      </form>

      {criteria.length === 0 && <p style={{ color: 'var(--color-muted)' }}>No custom criteria yet.</p>}

      {criteria.map((c) => (
        <div key={c.id} style={{ border: '1px solid var(--color-border)', borderRadius: 8, padding: 12, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>{c.name}</span>
            <span style={{ marginLeft: 8, fontSize: 13, color: 'var(--color-muted)' }}>
              {c.metric} {c.operator} {c.threshold} (weight: {c.weight})
            </span>
          </div>
          <button onClick={() => deleteMutation.mutate(c.id)}
            style={{ background: 'none', border: '1px solid var(--color-sell)', color: 'var(--color-sell)', borderRadius: 4, padding: '3px 10px', cursor: 'pointer', fontSize: 12 }}>
            Delete
          </button>
        </div>
      ))}
    </div>
  )
}

const inputStyle = {
  padding: '7px 10px',
  border: '1px solid var(--color-border)',
  borderRadius: 6,
  fontSize: 14,
  width: '100%',
  boxSizing: 'border-box' as const,
  background: 'var(--color-surface)',
  color: 'var(--color-text)',
}
