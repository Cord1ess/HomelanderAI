import {
  Anchor,
  Avatar,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core'
import {
  IconActivity,
  IconBuilding,
  IconCheck,
  IconClock,
  IconFileAnalytics,
  IconLogout,
  IconUser,
} from '@tabler/icons-react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { AuthProvider, useAuth } from './context/AuthContext'
import { AuthPage } from './pages/AuthPage'

function MainDashboard() {
  const { user, tenant, logout } = useAuth()

  return (
    <Box bg="var(--mantine-color-body)" mih="100vh" py={32}>
      <Container size="md">
        <Stack gap={24}>
          {/* ── Top Bar / Header ────────────────────────────────────────────── */}
          <Paper p="md" radius="md" withBorder bg="dark.7">
            <Group justify="space-between">
              <Group gap="sm">
                <ThemeIcon size={32} radius="md" color="clinical.5" variant="filled">
                  <IconActivity size={18} />
                </ThemeIcon>
                <Text ff="monospace" fw={700} size="lg" c="clinical.4">
                  HomelanderAI
                </Text>
                <Badge size="xs" color="clinical" variant="outline">
                  Portal
                </Badge>
              </Group>

              <Group gap="md">
                <Group gap="xs">
                  <Avatar color="clinical" radius="xl" size="sm">
                    <IconUser size={14} />
                  </Avatar>
                  <Stack gap={0}>
                    <Text fw={600} size="xs">
                      {user?.fullName ?? 'Underwriter'}
                    </Text>

                    <Text size="10px" c="dimmed">
                      {tenant?.name ?? 'Carrier'} ({user?.role ?? 'Role'})
                    </Text>
                  </Stack>
                </Group>

                <Button
                  variant="subtle"
                  color="gray"
                  size="xs"
                  leftSection={<IconLogout size={14} />}
                  onClick={logout}
                >
                  Sign Out
                </Button>
              </Group>
            </Group>
          </Paper>

          {/* ── Basic Dashboard Welcome Card ────────────────────────────────── */}
          <Card shadow="sm" radius="md" p="xl" withBorder bg="dark.8">
            <Stack gap="md">
              <Group justify="space-between" align="flex-start">
                <Stack gap={4}>
                  <Title order={2} size="h2">
                    Welcome back, {user?.fullName ?? 'Underwriter'}
                  </Title>
                  <Text size="sm" c="dimmed">
                    Signed in to <strong>{tenant?.name ?? 'Carrier Organization'}</strong> decision workspace.
                  </Text>
                </Stack>
                <Badge size="sm" color="teal" variant="light">
                  Session Active
                </Badge>
              </Group>

              {/* Baseline Metric Overview */}
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md" mt="sm">
                <Paper p="md" radius="md" withBorder bg="dark.7">
                  <Group justify="space-between" mb={4}>
                    <Text size="xs" c="dimmed" fw={600} tt="uppercase">
                      Active Cases
                    </Text>
                    <IconFileAnalytics size={16} color="var(--mantine-color-clinical-4)" />
                  </Group>
                  <Text fw={700} size="xl">
                    0
                  </Text>
                  <Text size="xs" c="dimmed" mt={2}>
                    Submitted evidence packages
                  </Text>
                </Paper>

                <Paper p="md" radius="md" withBorder bg="dark.7">
                  <Group justify="space-between" mb={4}>
                    <Text size="xs" c="dimmed" fw={600} tt="uppercase">
                      Pending Review
                    </Text>
                    <IconClock size={16} color="var(--mantine-color-yellow-5)" />
                  </Group>
                  <Text fw={700} size="xl">
                    0
                  </Text>
                  <Text size="xs" c="dimmed" mt={2}>
                    Awaiting human confirmation
                  </Text>
                </Paper>

                <Paper p="md" radius="md" withBorder bg="dark.7">
                  <Group justify="space-between" mb={4}>
                    <Text size="xs" c="dimmed" fw={600} tt="uppercase">
                      System Status
                    </Text>
                    <IconCheck size={16} color="var(--mantine-color-teal-4)" />
                  </Group>
                  <Text fw={700} size="sm" c="teal.3">
                    Operational
                  </Text>
                  <Text size="xs" c="dimmed" mt={2}>
                    Decision-support pipeline ready
                  </Text>
                </Paper>
              </SimpleGrid>

              {/* Placeholder Note */}
              <Paper p="sm" radius="sm" bg="dark.9" withBorder style={{ borderStyle: 'dashed' }} mt="xs">
                <Group gap="xs">
                  <IconBuilding size={16} color="var(--mantine-color-clinical-4)" />
                  <Text size="xs" c="dimmed">
                    Underwriting case management, DICOM imaging viewer, and model risk scoring features will be enabled in upcoming phases.
                  </Text>
                </Group>
              </Paper>
            </Stack>
          </Card>

          {/* ── Footer ──────────────────────────────────────────────────────── */}
          <Group justify="space-between">
            <Text size="xs" c="dimmed">
              HomelanderAI • Research software. Not a medical device.
            </Text>
            <Anchor href="/docs" target="_blank" size="xs" ff="monospace">
              /docs →
            </Anchor>
          </Group>
        </Stack>
      </Container>
    </Box>
  )
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/auth" element={<AuthPage />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <MainDashboard />
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
