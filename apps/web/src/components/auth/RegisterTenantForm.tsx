import {
  Alert,
  Anchor,
  Button,
  Grid,
  PasswordInput,
  Select,
  Stack,
  Text,
  TextInput,
} from '@mantine/core'
import { isEmail, useForm } from '@mantine/form'
import {
  IconAlertCircle,
  IconBadge,
  IconBuilding,
  IconLock,
  IconMail,
  IconUser,
} from '@tabler/icons-react'
import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import type { RegisterTenantPayload, UserRole } from '../../types/auth'

interface RegisterTenantFormProps {
  onSwitchToLogin?: () => void
}

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
      tenantName: (val) => (val.trim().length < 2 ? 'Carrier name must be at least 2 characters' : null),
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
      const message = err instanceof Error ? err.message : 'Registration failed. Please check input values.'
      setError(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={form.onSubmit(handleSubmit)}>
      <Stack gap="sm">
        {error && (
          <Alert color="red" variant="light" icon={<IconAlertCircle size={16} />} title="Registration Error">
            {error}
          </Alert>
        )}

        <Text size="xs" fw={700} tt="uppercase" c="dimmed" lts={0.5}>
          1. Subscribing Carrier Information
        </Text>

        <Grid>
          <Grid.Col span={{ base: 12, sm: 7 }}>
            <TextInput
              required
              label="Carrier / Organization Name"
              placeholder="e.g. Apex Life Assurance"
              leftSection={<IconBuilding size={16} />}
              {...form.getInputProps('tenantName')}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 5 }}>
            <Select
              required
              label="Subscription Tier"
              data={[
                { value: 'pilot', label: 'Pilot / Sandbox' },
                { value: 'standard', label: 'Standard Carrier' },
                { value: 'enterprise', label: 'Enterprise Multimodal' },
              ]}
              {...form.getInputProps('subscriptionTier')}
            />
          </Grid.Col>
        </Grid>

        <Text size="xs" fw={700} tt="uppercase" c="dimmed" lts={0.5} mt="xs">
          2. Initial Tenant Admin Account
        </Text>

        <Grid>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <TextInput
              required
              label="Admin Full Name"
              placeholder="Dr. Sarah Jenkins"
              leftSection={<IconUser size={16} />}
              {...form.getInputProps('adminFullName')}
            />
          </Grid.Col>

          <Grid.Col span={{ base: 12, sm: 6 }}>
            <TextInput
              required
              label="Work Email"
              placeholder="sarah.jenkins@apexlife.com"
              leftSection={<IconMail size={16} />}
              {...form.getInputProps('adminEmail')}
            />
          </Grid.Col>
        </Grid>

        <Grid>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <PasswordInput
              required
              label="Password"
              placeholder="Min. 8 characters"
              leftSection={<IconLock size={16} />}
              {...form.getInputProps('adminPassword')}
            />
          </Grid.Col>

          <Grid.Col span={{ base: 12, sm: 6 }}>
            <TextInput
              label="Underwriter License #"
              placeholder="e.g. FALU-98214 (optional)"
              leftSection={<IconBadge size={16} />}
              {...form.getInputProps('licenseNumber')}
            />
          </Grid.Col>
        </Grid>

        <Select
          label="Initial System Role"
          data={[
            { value: 'admin', label: 'Tenant Admin (Full System & User Management)' },
            { value: 'senior_underwriter', label: 'Senior Underwriter (Decision Sign-off & Audit)' },
            { value: 'underwriter', label: 'Medical Underwriter (Case Review)' },
          ]}
          value={form.values.role}
          onChange={(val) => form.setFieldValue('role', (val as UserRole) || 'admin')}
        />

        <Button type="submit" loading={submitting} color="clinical" fullWidth radius="md" mt="md">
          Register Carrier & Access Portal
        </Button>

        {onSwitchToLogin && (
          <Text size="xs" ta="center" c="dimmed" mt="xs">
            Already have a carrier account?{' '}
            <Anchor component="button" type="button" size="xs" onClick={onSwitchToLogin} fw={600}>
              Sign In
            </Anchor>
          </Text>
        )}
      </Stack>
    </form>
  )
}
