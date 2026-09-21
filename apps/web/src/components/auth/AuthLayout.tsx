import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { BrandIcon } from '../BrandIcon'

interface AuthLayoutProps {
  children: ReactNode
}

/**
 * Full-viewport split-panel auth shell.
 *
 * Left  — dark forest-green brand panel: logo, editorial serif headline, tagline.
 * Right — clean white form area.
 *
 * No Mantine layout components here — the auth shell has its own CSS class
 * (.auth-shell) so it can own its full-viewport grid without inheriting the
 * dark console theme that Mantine's defaultColorScheme='dark' would impose.
 */
export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="auth-shell">
      {/* ── Left — brand panel ─────────────────────────────────────── */}
      <div className="auth-panel-left">
        {/* Logo — links back to the public landing */}
        <Link
          to="/"
          className="auth-panel-left__logo"
          style={{ textDecoration: 'none' }}
        >
          <div className="auth-panel-left__logo-mark">
            <BrandIcon width={18} height={18} style={{ display: 'block', opacity: 0.9 }} />
          </div>
          <span className="auth-panel-left__logo-text">homelander</span>
        </Link>

        {/* Headline */}
        <div>
          <h1 className="auth-panel-left__headline">
            Calm focus for<br />consequential decisions.
          </h1>
          <p className="auth-panel-left__sub">
            One workspace for <em>evidence</em>, <em>judgment</em> and accountable{' '}
            <em>underwriting</em>.
          </p>
        </div>

        {/* Bottom quote */}
        <p className="auth-panel-left__quote">
          "Good software makes the next right action obvious."
        </p>
      </div>

      {/* ── Right — form panel ────────────────────────────────────── */}
      <div className="auth-panel-right">
        <div className="auth-panel-right__inner">
          {children}
        </div>
      </div>
    </div>
  )
}

