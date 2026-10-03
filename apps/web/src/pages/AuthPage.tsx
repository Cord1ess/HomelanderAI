import { Link, Navigate, useSearchParams } from 'react-router-dom'

import { AuthLayout } from '../components/auth/AuthLayout'
import { LoginForm } from '../components/auth/LoginForm'
import { BrandIcon } from '../components/BrandIcon'
import { ThemeToggle } from '../components/ThemeToggle'
import { useAuth } from '../context/AuthContext'
import { homeFor } from '../screens'

/**
 * The team's sign-in, and only the team's.
 *
 * Clients used to sign in from a second tab here, side by side with staff,
 * which read as though the two went together. A client never needs this
 * page: they check their application at /portal, which has its own clean
 * sign-in. Old links to the client tab are sent there.
 */
export function AuthPage() {
  const { isAuthenticated, isLoading, user } = useAuth()
  const [params] = useSearchParams()

  if (params.get('as') === 'client') return <Navigate to="/portal" replace />

  // Straight to the console, not to `/`: every button on the landing page
  // points back here, so a signed-in user sent there would bounce.
  if (!isLoading && isAuthenticated) {
    return <Navigate to={homeFor(user?.role)} replace />
  }

  return (
    <AuthLayout>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Link to="/" className="auth-panel-right__logo" style={{ textDecoration: 'none' }}>
            <div className="auth-panel-right__logo-mark">
              <BrandIcon width={16} height={16} style={{ display: 'block', opacity: 0.9 }} />
            </div>
            <span className="auth-panel-right__logo-text">Homelander AI</span>
          </Link>
          <ThemeToggle />
        </div>
        <p className="auth-eyebrow" style={{ marginTop: '2rem' }}>
          Team sign-in
        </p>
        <LoginForm />
        <p style={{ marginTop: '1.5rem', fontSize: '0.78rem', textAlign: 'center', color: 'var(--neo-muted)' }}>
          Applied for cover?{' '}
          <Link to="/portal" style={{ color: 'var(--neo-accent-deep)', fontWeight: 600 }}>
            Check your application here
          </Link>
          .
        </p>
      </div>
    </AuthLayout>
  )
}
