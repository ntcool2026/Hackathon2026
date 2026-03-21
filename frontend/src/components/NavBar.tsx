import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'

export default function NavBar() {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const isDark = theme === 'dark'

  return (
    <>
      {/* Slider styles scoped to nav */}
      <style>{`
        .theme-slider-wrap {
          display: flex;
          align-items: center;
          gap: 6px;
          cursor: pointer;
          user-select: none;
        }
        .theme-slider-track {
          position: relative;
          width: 44px;
          height: 24px;
          border-radius: 12px;
          background: var(--color-border);
          transition: background 0.25s;
          flex-shrink: 0;
        }
        .theme-slider-track.on {
          background: var(--color-primary);
        }
        .theme-slider-thumb {
          position: absolute;
          top: 3px;
          left: 3px;
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: #fff;
          transition: transform 0.25s;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 11px;
          line-height: 1;
          box-shadow: 0 1px 3px rgba(0,0,0,.3);
        }
        .theme-slider-thumb.on {
          transform: translateX(20px);
        }
      `}</style>

      <nav style={{
        position: 'sticky',
        top: 0,
        zIndex: 100,
        background: 'var(--color-surface)',
        borderBottom: '1px solid var(--color-border)',
        boxShadow: 'var(--shadow-nav)',
        height: 52,
        display: 'flex',
        alignItems: 'center',
        padding: '0 clamp(16px, 4vw, 32px)',
        gap: 16,
      }}>
        {/* Brand */}
        <Link
          to="/dashboard"
          style={{
            fontWeight: 700,
            fontSize: 16,
            color: 'var(--color-primary)',
            letterSpacing: '-0.3px',
            flexShrink: 0,
          }}
        >
          📈 Portfolio Advisor
        </Link>

        <div style={{ flex: 1 }} />

        <Link to="/preferences" style={{ fontSize: 13, color: 'var(--color-text-sub)' }}>Preferences</Link>
        <Link to="/criteria"    style={{ fontSize: 13, color: 'var(--color-text-sub)' }}>Criteria</Link>
        <Link to="/thresholds"  style={{ fontSize: 13, color: 'var(--color-text-sub)' }}>Alerts</Link>

        {/* Theme slider */}
        <div
          className="theme-slider-wrap"
          onClick={toggle}
          title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
          role="switch"
          aria-checked={isDark}
        >
          <div className={`theme-slider-track${isDark ? ' on' : ''}`}>
            <div className={`theme-slider-thumb${isDark ? ' on' : ''}`}>
              {isDark ? '🌙' : '☀️'}
            </div>
          </div>
        </div>

        {user && (
          <button
            onClick={logout}
            style={{
              background: 'none',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-pill)',
              padding: '4px 12px',
              fontSize: 12,
              color: 'var(--color-text-sub)',
              cursor: 'pointer',
            }}
          >
            Sign out
          </button>
        )}
      </nav>
    </>
  )
}
