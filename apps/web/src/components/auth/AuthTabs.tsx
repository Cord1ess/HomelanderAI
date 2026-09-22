import { Link, useSearchParams } from 'react-router-dom'
import { ClientLoginForm } from './ClientLoginForm'
import { LoginForm } from './LoginForm'
import { BrandIcon } from '../BrandIcon'
import { ThemeToggle } from '../ThemeToggle'

/**
 * Tab switcher for the auth right panel.
 * Renders its own logo, heading, and custom tab row — no Mantine Tabs.
 *
 * Two ways in, and no way to create an account. This is a B2B product: staff
 * accounts are made by a carrier's admin inside the console, and an applicant's
 * sign-in is generated when their application is taken. The carrier
 * registration form still exists at /auth/register-carrier, but nothing public
 * links to it.
 *
 * The tab lives in the URL (`/auth?as=client`) so the landing page can link
 * straight to the client side.
 */
export function AuthTabs() {
  const [params, setParams] = useSearchParams()
  const activeTab = params.get('as') === 'client' ? 'client' : 'staff'

  const show = (tab: 'staff' | 'client') =>
    setParams(tab === 'client' ? { as: 'client' } : {}, { replace: true })

  return (
    <div>
      {/* Logo — click to go back to landing */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Link to="/" className="auth-panel-right__logo" style={{ textDecoration: 'none' }}>
          <div className="auth-panel-right__logo-mark">
            <BrandIcon width={16} height={16} style={{ display: 'block', opacity: 0.9 }} />
          </div>
          <span className="auth-panel-right__logo-text">homelander</span>
        </Link>
        <ThemeToggle />
      </div>

      {/* Tab row */}
      <div className="auth-tab-row">
        <button
          type="button"
          className="auth-tab"
          data-active={activeTab === 'staff'}
          onClick={() => show('staff')}
        >
          Staff
        </button>
        <button
          type="button"
          className="auth-tab"
          data-active={activeTab === 'client'}
          onClick={() => show('client')}
        >
          Client
        </button>
      </div>

      {/* Forms */}
      {activeTab === 'staff' ? <LoginForm /> : <ClientLoginForm />}
    </div>
  )
}
