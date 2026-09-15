import { Alert } from '@mantine/core'
import { useForm } from '@mantine/form'
import { IconAlertCircle } from '@tabler/icons-react'
import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import type { LoginPayload } from '../../types/auth'

interface LoginFormProps {
  onSwitchToRegister?: () => void
}

/**
 * Sign-in form — clean white right panel style.
 * Labels and inputs are plain HTML with auth-* CSS classes to match the
 * screenshot design (no Mantine form controls, which carry console dark-mode
 * styling).
 */
export function LoginForm({ onSwitchToRegister }: LoginFormProps) {
  const { login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const form = useForm<LoginPayload>({
    initialValues: { email: '', password: '' },
    validate: {
      email: (val) => (val.trim().length < 1 ? 'Enter your email' : null),
      password: (val) => (val.length < 1 ? 'Password is required' : null),
    },
  })

  const handleSubmit = async (values: LoginPayload) => {
    setError(null)
    setSubmitting(true)
    try {
      await login(values)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Invalid email or password')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={form.onSubmit(handleSubmit)}>
      {/* Heading */}
      <h2 className="auth-heading">Welcome back.</h2>
      <p className="auth-subheading">
        Sign in to your <em>underwriting</em> workspace.
      </p>

      {error && (
        <Alert
          color="red"
          variant="light"
          icon={<IconAlertCircle size={15} />}
          mb="md"
          p="xs"
          style={{ fontSize: '0.8rem' }}
        >
          {error}
        </Alert>
      )}

      {/* Work email */}
      <div style={{ marginBottom: '1rem' }}>
        <label className="auth-label" htmlFor="login-email">Work email</label>
        <input
          id="login-email"
          type="text"
          className="auth-input"
          placeholder="you@carrier.com"
          autoComplete="email"
          {...form.getInputProps('email')}
        />
        {form.errors.email && (
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.72rem', color: '#c0392b' }}>
            {form.errors.email}
          </p>
        )}
      </div>

      {/* Password */}
      <div style={{ marginBottom: '1.5rem' }}>
        <label className="auth-label" htmlFor="login-password">Password</label>
        <input
          id="login-password"
          type="password"
          className="auth-input"
          placeholder="••••••••"
          autoComplete="current-password"
          {...form.getInputProps('password')}
        />
        {form.errors.password && (
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.72rem', color: '#c0392b' }}>
            {form.errors.password}
          </p>
        )}
      </div>

      {/* Submit */}
      <button type="submit" className="auth-btn-primary" disabled={submitting}>
        {submitting ? 'Signing in…' : 'Sign in →'}
      </button>

      {/* Switch to register */}
      {onSwitchToRegister && (
        <p style={{ marginTop: '1.25rem', fontSize: '0.78rem', textAlign: 'center', color: 'rgba(15,26,20,0.45)' }}>
          Need access?{' '}
          <button
            type="button"
            onClick={onSwitchToRegister}
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              fontSize: 'inherit',
              cursor: 'pointer',
              color: 'var(--neo-accent)',
              fontWeight: 600,
              textDecoration: 'underline',
              textUnderlineOffset: '2px',
            }}
          >
            Contact your workspace administrator
          </button>
        </p>
      )}
    </form>
  )
}

