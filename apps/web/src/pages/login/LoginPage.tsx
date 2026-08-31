import {
  Alert,
  Anchor,
  Box,
  Button,
  Group,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
} from '@mantine/core'
import { IconAlertCircle, IconArrowLeft, IconShieldLock } from '@tabler/icons-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { useAuth } from '../../auth/AuthContext'
import { BrandIcon } from '../../components/BrandIcon'

/**
 * Login — the one screen that lives OUTSIDE the guarded app shell.
 *
 * Email + password only: no signup, no reset, no SSO. In-memory (mock) session
 * for now — on success we record the user locally and land on the queue.
 *
 * Maybe-from URL:
 *   ?expired=1  → rendered as a "session expired, sign in again" banner
 *                (the RequireAuth guard redirects here when the in-memory
 *                session is lost, e.g. after a refresh).
 *
 * TODO: real flow when /api/auth/* lands:
 *   1. POST /api/auth/login  → server sets httpOnly cookie
 *   2. GET  /api/auth/me     → confirm identity, then navigate to /queue
 *   3. Any 401 → clear session + redirect here with ?expired=1
 * See docs/DashboardImplementation.md.
 */
export function LoginPage() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const expired = searchParams.get('expired') === '1'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)
    if (!email || !password) {
      setError('Enter your email and password to continue.')
      return
    }
    setSubmitting(true)
    // TODO: replace with POST /api/auth/login + GET /api/auth/me
    window.setTimeout(() => {
      setSubmitting(false)
      signIn(email.trim())
      navigate('/queue')
    }, 650)
  }

  return (
    <Box className="home-aurora" bg="var(--mantine-color-dark-9)" mih="100vh" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="home-grid" />

      <Box w="100%" px="md" style={{ maxWidth: 460 }}>
        <Paper
          p="xl"
          radius="md"
          className="home-rise home-rise-1"
          style={{ border: '1px solid var(--mantine-color-dark-6)', backgroundColor: 'var(--mantine-color-dark-8)' }}
        >
          <Stack gap="lg">
            <Stack align="center" gap="sm">
              <Paper className="home-brand-chip" p={5} radius="sm" w={104}>
                <BrandIcon width={94} height={44} style={{ display: 'block' }} />
              </Paper>
              <Stack gap={4} align="center">
                <Text size="lg" fw={700} ta="center">
                  Sign in to the console
                </Text>
                <Text size="sm" c="dimmed" ta="center">
                  Continue to the underwriting review queue.
                </Text>
              </Stack>
            </Stack>

            {expired && (
              <Alert color="yellow" variant="light" icon={<IconAlertCircle size={16} />}>
                <Stack gap={2}>
                  <Text size="sm" fw={600}>
                    Your session has expired
                  </Text>
                  <Text size="xs" c="dimmed">
                    Sign in again to continue where you left off.
                  </Text>
                </Stack>
              </Alert>
            )}

            <form onSubmit={handleSubmit} noValidate>
              <Stack gap="sm">
                <TextInput
                  label="Email"
                  placeholder="you@carrier.example"
                  required
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.currentTarget.value)}
                />
                <PasswordInput
                  label="Password"
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.currentTarget.value)}
                />

                {error && (
                  <Alert color="red" variant="light" icon={<IconAlertCircle size={16} />}>
                    <Text size="sm">{error}</Text>
                  </Alert>
                )}

                <Button type="submit" fullWidth color="clinical" loading={submitting} disabled={submitting}>
                  Sign in
                </Button>
              </Stack>
            </form>

            <Group justify="space-between" c="dimmed">
              <Anchor size="xs" component={Link} to="/">
                <Group gap={4}>
                  <IconArrowLeft size={12} />
                  Back to home
                </Group>
              </Anchor>
              <Group gap={4}>
                <IconShieldLock size={12} />
                <Text size="xs">Operator / underwriter access</Text>
              </Group>
            </Group>
          </Stack>
        </Paper>
      </Box>
    </Box>
  )
}
