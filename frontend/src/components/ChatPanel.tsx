import { useState, useRef, useEffect } from 'react'
import { apiFetch } from '../hooks/useApi'

const API = import.meta.env.VITE_API_URL ?? ''

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface ChatPanelProps {
  onClose: () => void
}

export default function ChatPanel({ onClose }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function send() {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setLoading(true)
    try {
      const res = await apiFetch(`${API}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      const data = await res.json()
      setMessages((prev) => [...prev, { role: 'assistant', content: data.answer ?? 'No response.' }])
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Failed to reach the advisor. Please try again.' }])
    } finally {
      setLoading(false)
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      right: 0,
      width: 360,
      height: '100dvh',
      background: 'var(--color-surface)',
      borderLeft: '1px solid var(--color-border)',
      display: 'flex',
      flexDirection: 'column',
      zIndex: 200,
      boxShadow: '-4px 0 24px rgba(0,0,0,0.12)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '14px 16px',
        borderBottom: '1px solid var(--color-border)',
        flexShrink: 0,
      }}>
        <span style={{ fontWeight: 700, fontSize: 15 }}>Portfolio Advisor</span>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--color-muted)', lineHeight: 1 }}
          title="Close"
        >
          ×
        </button>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {messages.length === 0 && (
          <p style={{ fontSize: 13, color: 'var(--color-muted)', textAlign: 'center', marginTop: 32 }}>
            Ask anything about the portfolio — risk, recommendations, sector exposure…
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '85%',
            background: m.role === 'user' ? 'var(--color-primary)' : 'var(--color-bg)',
            color: m.role === 'user' ? '#0a1118' : 'var(--color-text)',
            borderRadius: m.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
            padding: '8px 12px',
            fontSize: 13,
            lineHeight: 1.55,
            border: m.role === 'assistant' ? '1px solid var(--color-border)' : 'none',
          }}>
            {m.content}
          </div>
        ))}
        {loading && (
          <div style={{
            alignSelf: 'flex-start',
            background: 'var(--color-bg)',
            border: '1px solid var(--color-border)',
            borderRadius: '12px 12px 12px 2px',
            padding: '8px 14px',
            fontSize: 18,
            color: 'var(--color-muted)',
            letterSpacing: 2,
          }}>
            ···
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '10px 12px',
        borderTop: '1px solid var(--color-border)',
        display: 'flex',
        gap: 8,
        flexShrink: 0,
      }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask about the portfolio…"
          rows={2}
          style={{
            flex: 1,
            resize: 'none',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-sm)',
            padding: '7px 10px',
            fontSize: 13,
            background: 'var(--color-surface)',
            color: 'var(--color-text)',
            outline: 'none',
            fontFamily: 'inherit',
            lineHeight: 1.4,
          }}
          onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--color-primary)')}
          onBlur={(e) => (e.currentTarget.style.borderColor = 'var(--color-border)')}
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          style={{
            background: 'var(--color-primary)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            color: '#0a1118',
            fontWeight: 700,
            fontSize: 13,
            padding: '0 14px',
            cursor: loading || !input.trim() ? 'default' : 'pointer',
            opacity: loading || !input.trim() ? 0.5 : 1,
            flexShrink: 0,
          }}
        >
          Send
        </button>
      </div>
    </div>
  )
}
