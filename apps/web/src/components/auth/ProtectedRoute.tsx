import { Alert, Box, Center, Loader, Stack, Text } from '@mantine/core'
import { IconAlertTriangle } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import type { UserRole } from '../../types/auth'

interface ProtectedRouteProps {
  children: ReactNode
  allowedRoles?: UserRole[]
}

export function ProtectedRoute({ children, allowedRoles }: ProtectedRouteProps) {
  const { user, isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <Box bg="var(--mantine-color-body)" mih="100vh">
        <Center mih="100vh">
          <Stack align="center" gap="sm">
            <Loader color="clinical" size="lg" type="dots" />
            <Text size="sm" c="dimmed" ff="monospace">
              Checking your sign-in…
            </Text>
          </Stack>
        </Center>
      </Box>
    )
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/auth" replace />
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return (
      <Center mih="100vh" p="md">
        <Alert
          color="red"
          title="You do not have access"
          icon={<IconAlertTriangle size={20} />}
          style={{ maxWidth: 450 }}
        >
          <Text size="sm">
            Your account is set up as <strong>{user.role}</strong>, which cannot open
            this page. Ask an administrator at your company if you need access.
          </Text>
        </Alert>
      </Center>
    )
  }

  return <>{children}</>
}
