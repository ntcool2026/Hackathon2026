import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'

const WS_BASE = import.meta.env.VITE_WS_URL ?? `ws://${window.location.host}`
const MAX_BACKOFF_MS = 30_000

export interface PortfolioAnalysis {
  summary: string
  concentration_flags: string[]
}

export function useWebSocket(
  userId: string | null,
  _token: string | null,
  onPortfolioAnalysis?: (data: PortfolioAnalysis) => void,
) {
  const queryClient = useQueryClient()
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const backoffRef = useRef(1_000)
  const onPortfolioAnalysisRef = useRef(onPortfolioAnalysis)
  onPortfolioAnalysisRef.current = onPortfolioAnalysis

  useEffect(() => {
    if (!userId) return

    function connect() {
      const url = `${WS_BASE}/ws/${userId}`
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        backoffRef.current = 1_000 // reset on successful connect
      }

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data) as { event: string; payload: Record<string, unknown> }
          handleEvent(msg.event, msg.payload)
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        scheduleReconnect()
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    function handleEvent(event: string, payload: Record<string, unknown>) {
      const ticker = payload.ticker as string | undefined

      switch (event) {
        case 'score_update':
          if (ticker) {
            // Invalidate portfolio stock lists (where scores are embedded) and standalone score queries
            queryClient.invalidateQueries({ queryKey: ['stocks'] })
            queryClient.invalidateQueries({ queryKey: ['scores', ticker] })
            queryClient.invalidateQueries({ queryKey: ['scores'] })
          }
          break
        case 'rationale_update':
          if (ticker) {
            // Invalidate all portfolio stock queries so AI data refreshes immediately
            queryClient.invalidateQueries({ queryKey: ['stocks'] })
            queryClient.invalidateQueries({ queryKey: ['rationale', ticker] })
          }
          break
        case 'threshold_alert':
          if (ticker) {
            const score = payload.risk_score as number
            const threshold = payload.threshold as number
            // Simple browser notification fallback (toast library can replace this)
            console.warn(`Threshold alert: ${ticker} risk score ${score} crossed threshold ${threshold}`)
            if ('Notification' in window && Notification.permission === 'granted') {
              new Notification(`Threshold Alert: ${ticker}`, {
                body: `Risk score ${score.toFixed(1)} crossed your threshold of ${threshold}`,
              })
            }
          }
          break
        case 'data_stale':
          if (ticker) {
            queryClient.invalidateQueries({ queryKey: ['scores', ticker] })
          }
          break
        case 'portfolio_analysis':
          if (onPortfolioAnalysisRef.current) {
            onPortfolioAnalysisRef.current({
              summary: payload.summary as string,
              concentration_flags: (payload.concentration_flags as string[]) ?? [],
            })
          }
          break
      }
    }

    function scheduleReconnect() {
      const delay = Math.min(backoffRef.current, MAX_BACKOFF_MS)
      backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS)
      retryRef.current = setTimeout(connect, delay)
    }

    connect()

    return () => {
      if (retryRef.current) clearTimeout(retryRef.current)
      wsRef.current?.close()
    }
  }, [userId, queryClient])
}
