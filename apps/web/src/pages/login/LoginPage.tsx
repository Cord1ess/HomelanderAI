import {
  Alert,
  Anchor,
  Box,
  Button,
  Group,
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
 * Neo-brutalist persona to match the home page: light background, hard black
 * borders, chunky shadows, dark ink text. Behaviour is unchanged:
 *
 *   • Email + password only. In-memory (mock) session — accepts any non-empty
 *     pair for now; see docs/DashboardImplementation.md for the real contract.
 *   • ?expired=1  → "session expired" banner (RequireAuth redirects here when
 *     the in-memory session is lost, e.g. after a refresh).
 *   • On success → /queue. The submit button is disabled/loading in-flight.
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
    <Box className="neo-shell" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' }}>
      <Box w="100%" style={{ maxWidth: 480 }}>
        {expired && (
          <Alert
            color="yellow"
            radius={0}
            icon={<IconAlertCircle size={18} />}
            style={{
              border: '3px solid var(--neo-ink)',
              boxShadow: '6px 6px 0 var(--neo-ink)',
              backgroundColor: '#fff3bf',
              marginBottom: '1.5rem',
            }}
          >
            <Stack gap={2}>
              <Text size="sm" fw={800} c="var(--neo-ink)">
                Your session has expired
              </Text>
              <Text size="xs" c="var(--neo-ink)" opacity={0.75}>
                Sign in again to continue where you left off.
              </Text>
            </Stack>
          </Alert>
        )}

        <Box className="neo-card" p="xl">
          <Stack gap="lg">
            <Stack align="center" gap="sm">
              <Box className="neo-brand-chip" p={6}>
                <BrandIcon width={104} height={50} style={{ display: 'block' }} />
              </Box>
              <Stack gap={4} align="center">
                <Text className="neo-display" style={{ fontSize: '1.5rem' }} ta="center">
                  Sign in to the console
                </Text>
                <Text size="sm" c="var(--neo-ink)" opacity={0.72} ta="center">
                  Continue to the underwriting review queue.
                </Text>
              </Stack>
            </Stack>

            <form onSubmit={handleSubmit} noValidate>
              <Stack gap="sm">
                <TextInput
                  label="Email"
                  placeholder="you@carrier.example"
                  required
                  autoComplete="username"
                  size="md"
                  styles={{ input: { border: '2px solid var(--neo-ink)', borderRadius: 0 }, label: { fontWeight: 700 } }}
                  value={email}
                  onChange={(e) => setEmail(e.currentTarget.value)}
                />
                <PasswordInput
                  label="Password"
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                  size="md"
                  styles={{ input: { border: '2px solid var(--neo-ink)', borderRadius: 0 }, label: { fontWeight: 700 } }}
                  value={password}
                  onChange={(e) => setPassword(e.currentTarget.value)}
                />

                {error && (
                  <Alert
                    color="red"
                    radius={0}
                    icon={<IconAlertCircle size={16} />}
                    style={{ border: '2px solid var(--neo-ink)', backgroundColor: '#ffc9c9' }}
                  >
                    <Text size="sm" fw={700} c="var(--neo-ink)">
                      {error}
                    </Text>
                  </Alert>
                )}

                <Box className="neo-press">
                  <Button
                    type="submit"
                    fullWidth
                    size="lg"
                    radius={0}
                    color="clinical"
                    loading={submitting}
                    disabled={submitting}
                    style={{ border: '3px solid var(--neo-ink)', boxShadow: '6px 6px 0 var(--neo-accent)', fontWeight: 800 }}
                  >
                    Sign in
                  </Button>
                </Box>
              </Stack>
            </form>

            <Group justify="space-between" wrap="wrap">
              <Anchor size="xs" component={Link} to="/" style={{ fontWeight: 700, color: 'var(--neo-ink)' }}>
                <Group gap={4}>
                  <IconArrowLeft size={12} />
                  Back to home
                </Group>
              </Anchor>
              <Group gap={4} c="var(--neo-ink)" opacity={0.7}>
                <IconShieldLock size={12} />
                <Text size="xs" fw={600}>
                  Operator / underwriter access
                </Text>
              </Group>
            </Group>
          </Stack>
        </Box>
      </Box>
    </Box>
  )
}
