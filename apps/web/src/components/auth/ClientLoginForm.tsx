import { Alert } from '@mantine/core'
import { useForm } from '@mantine/form'
import { IconAlertCircle } from '@tabler/icons-react'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { portalLogin } from '../../api/client'

interface ClientLoginValues {
  portalId: string
  password: string
}

/**
 * Applicant sign-in. Same plain-HTML, auth-* styling as the staff form so the
 * two tabs read as one page.
 *
 * It does not touch AuthContext: an applicant is not a console user, and the
 * portal has its own cookie. The status that sign-in returns is put straight
 * into the query cache so the portal opens without a second request.
 */
export function ClientLoginForm() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const form = useForm<ClientLoginValues>({
    initialValues: { portalId: '', password: '' },
    validate: {
      portalId: (val) => (val.trim().length < 1 ? 'Enter your portal ID' : null),
      password: (val) => (val.length < 1 ? 'Password is required' : null),
    },
  })

  const handleSubmit = async (values: ClientLoginValues) => {
    setError(null)
    setSubmitting(true)
    try {
      const status = await portalLogin({
        portalId: values.portalId.trim(),
        password: values.password,
      })
      queryClient.setQueryData(['portal', 'me'], status)
      navigate('/portal', { replace: true })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'That portal ID and password do not match.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={form.onSubmit(handleSubmit)}>
      <h2 className="auth-heading">Your application.</h2>
      <p className="auth-subheading">
        See where it stands and when to expect an <em>answer</em>.
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

      <div style={{ marginBottom: '1rem' }}>
        <label className="auth-label" htmlFor="portal-id">Portal ID</label>
        <input
          id="portal-id"
          type="text"
          className="auth-input"
          placeholder="HC-XXXXXXXX"
          autoComplete="username"
          autoCapitalize="characters"
          spellCheck={false}
          {...form.getInputProps('portalId')}
        />
        {form.errors.portalId && (
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.72rem', color: 'var(--neo-danger)' }}>
            {form.errors.portalId}
          </p>
        )}
      </div>

      <div style={{ marginBottom: '1.5rem' }}>
        <label className="auth-label" htmlFor="portal-password">Password</label>
        <input
          id="portal-password"
          type="password"
          className="auth-input"
          placeholder="••••••••"
          autoComplete="current-password"
          {...form.getInputProps('password')}
        />
        {form.errors.password && (
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.72rem', color: 'var(--neo-danger)' }}>
            {form.errors.password}
          </p>
        )}
      </div>

      <button type="submit" className="auth-btn-primary" disabled={submitting}>
        {submitting ? 'Signing in…' : 'Open my application →'}
      </button>

      <p style={{ marginTop: '1.25rem', fontSize: '0.78rem', textAlign: 'center', color: 'var(--neo-muted)' }}>
        Your portal ID and password were given to you when you applied, by email
        or by the person who took your application.
      </p>
    </form>
  )
}
