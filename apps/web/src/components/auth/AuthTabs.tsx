import { useState } from 'react'
import { Link } from 'react-router-dom'
import { LoginForm } from './LoginForm'
import { RegisterTenantForm } from './RegisterTenantForm'
import { BrandIcon } from '../BrandIcon'

/**
 * Tab switcher for the auth right panel.
 * Renders its own logo, heading, and custom tab row — no Mantine Tabs.
 */
export function AuthTabs() {
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login')

  return (
    <div>
      {/* Logo — click to go back to landing */}
      <Link to="/" className="auth-panel-right__logo" style={{ textDecoration: 'none' }}>
        <div className="auth-panel-right__logo-mark">
          <BrandIcon width={16} height={16} style={{ display: 'block', opacity: 0.9 }} />
        </div>
        <span className="auth-panel-right__logo-text">homelander</span>
      </Link>

      {/* Tab row */}
      <div className="auth-tab-row">
        <button
          type="button"
          className="auth-tab"
          data-active={activeTab === 'login'}
          onClick={() => setActiveTab('login')}
        >
          Sign in
        </button>
        <button
          type="button"
          className="auth-tab"
          data-active={activeTab === 'register'}
          onClick={() => setActiveTab('register')}
        >
          Create account
        </button>
      </div>

      {/* Forms */}
      {activeTab === 'login' ? (
        <LoginForm onSwitchToRegister={() => setActiveTab('register')} />
      ) : (
        <RegisterTenantForm onSwitchToLogin={() => setActiveTab('login')} />
      )}
    </div>
  )
}

