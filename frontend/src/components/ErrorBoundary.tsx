import React from 'react'

interface Props {
  children: React.ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      const isApiError = this.state.error?.message?.includes('Failed to fetch') ||
        this.state.error?.message?.includes('NetworkError') ||
        this.state.error?.message?.includes('Load failed')

      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
          padding: 24,
          fontFamily: 'system-ui, sans-serif',
        }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8, color: '#ff4757' }}>
            Something went wrong
          </h1>
          {isApiError ? (
            <div style={{ textAlign: 'center', maxWidth: 480 }}>
              <p style={{ color: '#666', marginBottom: 12 }}>
                Cannot connect to the API server. This usually means the{' '}
                <code style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: 3 }}>VITE_API_URL</code>{' '}
                environment variable is not set on your Render frontend service.
              </p>
              <p style={{ color: '#888', fontSize: 13, marginBottom: 16 }}>
                Set it to your backend's Render URL (e.g.{' '}
                <code style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: 3 }}>
                  https://portfolio-advisor-api.onrender.com
                </code>
                )
              </p>
              <code style={{ display: 'block', background: '#1a1a2e', color: '#e0e0e0', padding: 12, borderRadius: 6, fontSize: 12, textAlign: 'left', marginBottom: 16 }}>
                {this.state.error?.message}
              </code>
            </div>
          ) : (
            <p style={{ color: '#666', marginBottom: 16 }}>{this.state.error?.message}</p>
          )}
          <button
            onClick={() => window.location.reload()}
            style={{
              background: '#0a1118',
              color: '#fff',
              border: 'none',
              borderRadius: 6,
              padding: '10px 24px',
              fontSize: 14,
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Reload page
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
