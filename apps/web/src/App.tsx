import {
  Alert,
  Anchor,
  Badge,
  Box,
  Card,
  Code,
  Container,
  Divider,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core'
import { IconAlertTriangle } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import type { CSSProperties, ReactNode } from 'react'

import { getHealth } from './api/client'

/**
 * Phase 0 landing page.
 *
 * Doubles as the reference implementation of the polling pattern the job
 * pipeline will need — `useQuery` with `refetchInterval` is exactly how the
 * applicant job status view will work.
 */

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <Text className="hl-eyebrow" c="dimmed">
      {children}
    </Text>
  )
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Group justify="space-between" gap="xl" wrap="nowrap">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="sm" ff="monospace" ta="right">
        {value}
      </Text>
    </Group>
  )
}

function Dot({ color, live }: { color: string; live: boolean }) {
  return (
    <Box
      className="hl-dot"
      data-live={live}
      style={{ '--hl-dot-color': color } as CSSProperties}
    />
  )
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${Math.round(seconds % 60)}s`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

const INSTALLED = [
  {
    group: 'Frontend',
    items: ['React 19 + Vite', 'Mantine 9', 'TanStack Query', 'React Router', 'Recharts'],
  },
  {
    group: 'Backend',
    items: ['FastAPI', 'Pydantic v2', 'SQLAlchemy 2 + Alembic', 'Celery + Redis', 'structlog'],
  },
  {
    group: 'Optional extras',
    items: [
      'torch (CPU) + TorchXRayVision',
      'XGBoost + scikit-learn',
      'SHAP + Grad-CAM',
      'spaCy + scispaCy',
      'MLflow',
    ],
  },
]

const PHASE_ONE = [
  ['PostgreSQL', 'tenant_id + row-level security'],
  ['Redis + Celery', 'async inference jobs, Flower dashboard'],
  ['MinIO', 'evidence packages and heatmap artifacts'],
  ['Auth', 'JWT session cookie + hashed carrier API keys'],
  ['Alembic', 'baseline migration and schema'],
]

export function App() {
  const { data, error, isPending } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 5_000,
  })

  const online = Boolean(data) && !error

  return (
    <Box bg="var(--mantine-color-body)" mih="100vh" py={64}>
      <Container size={680}>
        <Stack gap={40}>
          {/* ── Header ─────────────────────────────────────── */}
          <Stack gap={6}>
            <Group gap="sm">
              <Text ff="monospace" fw={700} size="sm" c="clinical.4">
                ▚
              </Text>
              <Text ff="monospace" fw={600} size="sm">
                HomelanderAI
              </Text>
              <Badge size="xs" color="gray" radius="sm">
                Phase 0
              </Badge>
            </Group>
            <Title order={1}>Development environment</Title>
            <Text c="dimmed" size="sm">
              Scaffold only — no pipeline, no models, no database yet. Everything below is
              installed and ready to build on.
            </Text>
          </Stack>

          {/* ── API status ─────────────────────────────────── */}
          <Stack gap="xs">
            <Eyebrow>API connection</Eyebrow>
            <Card>
              <Group justify="space-between" wrap="nowrap">
                <Group gap="sm" wrap="nowrap">
                  <Dot
                    color={
                      online
                        ? 'var(--mantine-color-teal-5)'
                        : isPending
                          ? 'var(--mantine-color-yellow-5)'
                          : 'var(--mantine-color-red-6)'
                    }
                    live={online}
                  />
                  <Text size="sm" fw={500}>
                    {online ? 'Server is running' : isPending ? 'Connecting…' : 'Not reachable'}
                  </Text>
                </Group>
                <Code>GET /api/health</Code>
              </Group>

              {data && (
                <>
                  <Divider my="md" />
                  <Stack gap={8}>
                    <Row label="Service" value={data.service} />
                    <Row label="Version" value={data.version} />
                    <Row label="Environment" value={data.environment} />
                    <Row label="Uptime" value={formatUptime(data.uptime_seconds)} />
                  </Stack>
                  <Text size="xs" c="dimmed" mt="md">
                    Polling every 5s via TanStack Query — the same pattern the inference job
                    view will use.
                  </Text>
                </>
              )}

              {error && (
                <>
                  <Divider my="md" />
                  <Alert
                    color="red"
                    variant="light"
                    icon={<IconAlertTriangle size={16} />}
                    title="Start the API"
                  >
                    <Stack gap={6}>
                      <Text size="sm">{error.message}</Text>
                      <Code block>
                        cd apps/api{'\n'}uv run uvicorn app.main:app --reload
                      </Code>
                    </Stack>
                  </Alert>
                </>
              )}
            </Card>
          </Stack>

          {/* ── Installed ──────────────────────────────────── */}
          <Stack gap="xs">
            <Eyebrow>Installed</Eyebrow>
            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
              {INSTALLED.map(({ group, items }) => (
                <Card key={group} padding="md">
                  <Text size="xs" fw={600} mb={8}>
                    {group}
                  </Text>
                  <Stack gap={4}>
                    {items.map((item) => (
                      <Text key={item} size="xs" c="dimmed" ff="monospace">
                        {item}
                      </Text>
                    ))}
                  </Stack>
                </Card>
              ))}
            </SimpleGrid>
            <Text size="xs" c="dimmed">
              The optional extras are declared but not installed by default. Run{' '}
              <Code>uv sync --extra ml</Code> only if you are working on models.
            </Text>
          </Stack>

          {/* ── Next phase ─────────────────────────────────── */}
          <Stack gap="xs">
            <Eyebrow>Wired up next</Eyebrow>
            <Card padding="md">
              <Stack gap={10}>
                {PHASE_ONE.map(([name, detail]) => (
                  <Group key={name} justify="space-between" gap="xl" wrap="nowrap">
                    <Group gap="sm" wrap="nowrap">
                      <Dot color="var(--mantine-color-dark-3)" live={false} />
                      <Text size="sm" ff="monospace">
                        {name}
                      </Text>
                    </Group>
                    <Text size="xs" c="dimmed" ta="right">
                      {detail}
                    </Text>
                  </Group>
                ))}
              </Stack>
            </Card>
          </Stack>

          {/* ── Footer ─────────────────────────────────────── */}
          <Group justify="space-between">
            <Text size="xs" c="dimmed">
              Research software. Not a medical device.
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
