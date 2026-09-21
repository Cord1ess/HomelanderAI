import { Alert } from '@mantine/core'
import { isEmail, useForm } from '@mantine/form'
import { IconAlertCircle } from '@tabler/icons-react'
import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import type { RegisterTenantPayload, UserRole } from '../../types/auth'

interface RegisterTenantFormProps {
  onSwitchToLogin?: () => void
}

/**
 * Carrier registration form — same clean white panel style as LoginForm.
 * Uses plain HTML inputs with auth-* CSS classes.
 */
export function RegisterTenantForm({ onSwitchToLogin }: RegisterTenantFormProps) {
  const { registerTenant } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const form = useForm<RegisterTenantPayload>({
    initialValues: {
      tenantName: '',
      subscriptionTier: 'standard',
      adminFullName: '',
      adminEmail: '',
      adminPassword: '',
      licenseNumber: '',
      role: 'admin',
    },
    validate: {
      tenantName: (val) => (val.trim().length < 2 ? 'Enter your company name' : null),
      adminFullName: (val) => (val.trim().length < 2 ? 'Full name is required' : null),
      adminEmail: isEmail('Please enter a valid work email address'),
      adminPassword: (val) => (val.length < 8 ? 'Password must be at least 8 characters' : null),
    },
  })

  const handleSubmit = async (values: RegisterTenantPayload) => {
    setError(null)
    setSubmitting(true)
    try {
      await registerTenant(values)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed. Please check your inputs.')
    } finally {
      setSubmitting(false)
    }
  }

  const field = (
    id: string,
    label: string,
    type: 'text' | 'email' | 'password',
    placeholder: string,
    inputProps: object,
    error?: string | null,
    required = true,
  ) => (
    <div style={{ marginBottom: '0.85rem' }}>
      <label className="auth-label" htmlFor={id}>
        {label}{required && <span style={{ color: 'var(--neo-accent)', marginLeft: 2 }}>*</span>}
      </label>
      <input
        id={id}
        type={type}
        className="auth-input"
        placeholder={placeholder}
        {...inputProps}
      />
      {error && (
        <p style={{ margin: '0.2rem 0 0', fontSize: '0.7rem', color: '#c0392b' }}>{error}</p>
      )}
    </div>
  )

  return (
    <form onSubmit={form.onSubmit(handleSubmit)}>
      <h2 className="auth-heading">Create an account.</h2>
      <p className="auth-subheading">
        Register your <em>carrier</em> and set up the admin account.
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

      {/* Section 1 — Carrier */}
      <p style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(15,26,20,0.4)', marginBottom: '0.65rem' }}>
        1. Carrier
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '0.65rem', marginBottom: '0.85rem' }}>
        <div>
          <label className="auth-label" htmlFor="reg-company">
            Company name<span style={{ color: 'var(--neo-accent)', marginLeft: 2 }}>*</span>
          </label>
          <input
            id="reg-company"
            type="text"
            className="auth-input"
            placeholder="Apex Life Assurance"
            {...form.getInputProps('tenantName')}
          />
          {form.errors.tenantName && (
            <p style={{ margin: '0.2rem 0 0', fontSize: '0.7rem', color: '#c0392b' }}>{form.errors.tenantName}</p>
          )}
        </div>
        <div>
          <label className="auth-label" htmlFor="reg-plan">Plan</label>
          <select
            id="reg-plan"
            className="auth-input"
            style={{ cursor: 'pointer' }}
            value={form.values.subscriptionTier}
            onChange={(e) => form.setFieldValue('subscriptionTier', e.target.value as RegisterTenantPayload['subscriptionTier'])}
          >
            <option value="pilot">Trial</option>
            <option value="standard">Standard</option>
            <option value="enterprise">Enterprise</option>
          </select>
        </div>
      </div>

      {/* Section 2 — Admin account */}
      <p style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(15,26,20,0.4)', marginBottom: '0.65rem', marginTop: '0.25rem' }}>
        2. Admin account
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.65rem' }}>
        {field('reg-name', 'Full name', 'text', 'Dr. Sarah Jenkins', form.getInputProps('adminFullName'), form.errors.adminFullName as string)}
        {field('reg-email', 'Work email', 'email', 'sarah@apexlife.com', form.getInputProps('adminEmail'), form.errors.adminEmail as string)}
        {field('reg-password', 'Password', 'password', 'Min. 8 characters', form.getInputProps('adminPassword'), form.errors.adminPassword as string)}
        {field('reg-license', 'Licence number', 'text', 'FALU-98214 (optional)', form.getInputProps('licenseNumber'), null, false)}
      </div>

      {/* Role */}
      <div style={{ marginBottom: '1.5rem', marginTop: '0.85rem' }}>
        <label className="auth-label" htmlFor="reg-role">Your role</label>
        <select
          id="reg-role"
          className="auth-input"
          style={{ cursor: 'pointer' }}
          value={form.values.role}
          onChange={(e) => form.setFieldValue('role', e.target.value as UserRole)}
        >
          <option value="admin">Administrator — manages staff accounts and settings</option>
          <option value="medical_professional">Medical Professional — decides escalated cases</option>
          <option value="underwriter">Underwriter — reviews applications</option>
        </select>
      </div>

      <button type="submit" className="auth-btn-primary" disabled={submitting}>
        {submitting ? 'Creating account…' : 'Create account →'}
      </button>

      {onSwitchToLogin && (
        <p style={{ marginTop: '1.25rem', fontSize: '0.78rem', textAlign: 'center', color: 'rgba(15,26,20,0.45)' }}>
          Already have an account?{' '}
          <button
            type="button"
            onClick={onSwitchToLogin}
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
            Sign in
          </button>
        </p>
      )}
    </form>
  )
}

