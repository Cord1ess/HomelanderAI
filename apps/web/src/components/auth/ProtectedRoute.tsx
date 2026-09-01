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
              Verifying carrier session…
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
          title="Access Restricted"
          icon={<IconAlertTriangle size={20} />}
          style={{ maxWidth: 450 }}
        >
          <Text size="sm">
            Your system role (<strong>{user.role}</strong>) does not have authorization to view this
            resource. Contact your Carrier Tenant Admin for permissions.
          </Text>
        </Alert>
      </Center>
    )
  }

  return <>{children}</>
}
