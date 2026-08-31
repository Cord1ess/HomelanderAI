import {
  Alert,
  Button,
  Card,
  Container,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { IconAlertCircle } from '@tabler/icons-react'
import { useState } from 'react'

/**
 * Login — email + password + submit. No signup, no reset, no SSO.
 *
 * On success the API sets an httpOnly cookie; the frontend then reports who is
 * logged in via `GET /api/auth/me`. A 401 anywhere redirects to /login.
 *
 * TODO: call `POST /api/auth/login`, then `GET /api/auth/me`, then navigate to
 * the queue. Handle 401 → redirect in a shared client/guard layer.
 */
export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  return (
    <Container size={420} py={80}>
      <Card padding="xl">
        <Stack gap="md">
          <Stack gap={2}>
            <Text ff="monospace" fw={700} size="sm" c="clinical.4">
              ▚ HomelanderAI
            </Text>
            <Title order={1}>Sign in</Title>
            <Text size="sm" c="dimmed">
              Operator or underwriter access.
            </Text>
          </Stack>

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

          <Alert color="red" variant="light" icon={<IconAlertCircle size={16} />}>
            <Text size="sm">Link the login mutation here.</Text>
          </Alert>

          <Button type="submit" fullWidth>
            Sign in
          </Button>
        </Stack>
      </Card>
    </Container>
  )
}
