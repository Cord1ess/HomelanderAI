import {
  Alert,
  Anchor,
  Button,
  Group,
  PasswordInput,
  Stack,
  Text,
  TextInput,
} from '@mantine/core'
import { isEmail, useForm } from '@mantine/form'
import { IconAlertCircle, IconBuilding, IconLock, IconMail } from '@tabler/icons-react'
import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import type { LoginPayload } from '../../types/auth'

interface LoginFormProps {
  onSwitchToRegister?: () => void
}

export function LoginForm({ onSwitchToRegister }: LoginFormProps) {
  const { login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const form = useForm<LoginPayload>({
    initialValues: {
      email: '',
      password: '',
      tenantSlug: '',
    },
    validate: {
      email: isEmail('Please enter a valid work email address'),
      password: (val) => (val.length < 1 ? 'Password is required' : null),
    },
  })

  const handleSubmit = async (values: LoginPayload) => {
    setError(null)
    setSubmitting(true)
    try {
      await login(values)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Invalid email or password'
      setError(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={form.onSubmit(handleSubmit)}>
      <Stack gap="md">
        {error && (
          <Alert color="red" variant="light" icon={<IconAlertCircle size={16} />} title="Sign In Error">
            {error}
          </Alert>
        )}

        <TextInput
          required
          label="Work Email"
          placeholder="underwriter@carrier.com"
          leftSection={<IconMail size={16} />}
          {...form.getInputProps('email')}
        />

        <PasswordInput
          required
          label="Password"
          placeholder="Your password"
          leftSection={<IconLock size={16} />}
          {...form.getInputProps('password')}
        />

        <TextInput
          label="Carrier Organization Slug"
          placeholder="e.g. met-life (optional)"
          leftSection={<IconBuilding size={16} />}
          description="Specify if your account is bound to a specific carrier domain"
          {...form.getInputProps('tenantSlug')}
        />

        <Group justify="space-between" mt="xs">
          <Anchor component="button" type="button" size="xs" c="dimmed">
            Forgot password?
          </Anchor>
        </Group>

        <Button type="submit" loading={submitting} color="clinical" fullWidth radius="md" mt="sm">
          Sign In to Portal
        </Button>

        {onSwitchToRegister && (
          <Text size="xs" ta="center" c="dimmed" mt="xs">
            Need to register a new carrier?{' '}
            <Anchor component="button" type="button" size="xs" onClick={onSwitchToRegister} fw={600}>
              Onboard Carrier Organization
            </Anchor>
          </Text>
        )}
      </Stack>
    </form>
  )
}
