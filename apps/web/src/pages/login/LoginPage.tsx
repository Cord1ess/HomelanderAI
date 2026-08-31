import {
  Alert,
  Anchor,
  Box,
  Button,
  Card,
  Center,
  Divider,
  Group,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
} from '@mantine/core'
import { IconAlertCircle, IconShieldLock } from '@tabler/icons-react'
import { useState, type FormEvent } from 'react'

import { BrandIcon } from '../../components/BrandIcon'

/**
 * Login — the one screen that lives OUTSIDE the guarded app shell.
 *
 * Email + password only: no signup, no reset, no SSO. On success the API sets
 * an httpOnly cookie; the frontend then confirms who is signed in via
 * `GET /api/auth/me`, and all 401s redirect back here.
 *
 * TODO: call `POST /api/auth/login`, then `GET /api/auth/me`, then navigate to
 * the queue.
 */
export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [touched, setTouched] = useState(false)

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setTouched(true)
    if (!email || !password) return
    setSubmitting(true)
    // TODO: POST /api/auth/login, then GET /api/auth/me, then navigate to "/".
    window.setTimeout(() => setSubmitting(false), 900)
  }

  const showError = touched && (!email || !password)

  return (
    <Box h="100vh" style={{ display: 'flex', alignItems: 'center' }}>
      <Paper
        radius={0}
        w={280}
        h="100%"
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 14,
          textAlign: 'center',
        }}
        visibleFrom="sm"
      >
        <BrandIcon width={200} height={80} />
        <Text size="xs" c="dimmed" px="lg">
          AI-assisted respiratory underwriting for carriers.
        </Text>
        <Divider my="md" w="70%" />
        <Group gap={6} c="dimmed">
          <IconShieldLock size={16} />
          <Text size="xs">Operator / underwriter access</Text>
        </Group>
      </Paper>

      <Center m="auto" px="xl" w="100%" style={{ maxWidth: 460 }}>
        <Card w="100%" padding="xl" radius="md">
          <Stack gap="md" hiddenFrom="sm" align="center">
            <BrandIcon width={200} height={70} />
          </Stack>

          <Stack gap={4} mb="lg">
            <Text size="lg" fw={600}>
              Sign in
            </Text>
            <Text size="sm" c="dimmed">
              Continue to the review queue.
            </Text>
          </Stack>

          <form onSubmit={handleSubmit} noValidate>
            <Stack gap="sm">
              <TextInput
                label="Email"
                placeholder="you@carrier.example"
                required
                value={email}
                onChange={(e) => setEmail(e.currentTarget.value)}
              />
              <PasswordInput
                label="Password"
                placeholder="••••••••"
                required
                value={password}
                onChange={(e) => setPassword(e.currentTarget.value)}
              />

              {showError && (
                <Alert color="red" variant="light" icon={<IconAlertCircle size={16} />}>
                  <Text size="sm">Enter your email and password.</Text>
                </Alert>
              )}

              <Button type="submit" fullWidth loading={submitting}>
                Sign in
              </Button>

              <Text size="xs" c="dimmed" ta="center">
                Trouble signing in?{' '}
                <Anchor size="xs" href="#" onClick={(e) => e.preventDefault()}>
                  Contact support
                </Anchor>
              </Text>
            </Stack>
          </form>
        </Card>
      </Center>
    </Box>
  )
}
