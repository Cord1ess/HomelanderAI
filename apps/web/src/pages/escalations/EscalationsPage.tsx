import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Group,
  Paper,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core'
import {
  IconAlertCircle,
  IconCheck,
  IconClock,
  IconEye,
  IconFlame,
  IconRefresh,
  IconSearch,
  IconShieldCheck,
  IconStethoscope,
} from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { getQueue, type QueueItem } from '../../api/client'
import { TierBadge } from '../../components/TierBadge'

/**
 * Senior Underwriter & Medical Officer Escalations Command Center.
 *
 * Dedicated clinical workbench for managing mandatory Tier 3 (Elevated Risk)
 * escalations, reviewing sub-score breakdowns, and issuing binding decisions.
 */

function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return days === 1 ? 'yesterday' : `${days}d ago`
}

export function EscalationsPage() {
  const [query, setQuery] = useState('')

  const { data, isPending, isFetching, error, refetch } = useQuery({
    queryKey: ['escalations', query],
    queryFn: () => getQueue({ q: query }),
    refetchInterval: 20_000,
    placeholderData: keepPreviousData,
  })

  // Filter specifically for escalated / Tier 3 items
  const allItems = data?.items ?? []
  const escalatedRows = allItems.filter(
    (item) => item.tier === 'elevated' || (item.crs != null && item.crs > 45),
  )

  const pendingDecisionCount = escalatedRows.filter((item) => item.status !== 'decided').length
  const decidedCount = escalatedRows.filter((item) => item.status === 'decided').length
  const avgCrs =
    escalatedRows.length > 0
      ? (
          escalatedRows.reduce((acc, curr) => acc + (curr.crs ?? 0), 0) / escalatedRows.length
        ).toFixed(1)
      : '—'

  return (
    <Stack gap="md">
      {/* ── Header ─────────────────────────────────────────── */}
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Group gap="xs" align="center">
            <Text size="lg" fw={700}>
              Senior Escalations Command Center
            </Text>
            <Badge color="grape" variant="filled" size="sm" leftSection={<IconFlame size={12} />}>
              Medical Officer Review
            </Badge>
          </Group>
          <Text size="xs" c="dimmed">
            Mandatory human-in-the-loop review queue for Tier 3 (Elevated Risk) policy applications
          </Text>
        </div>
        <Group gap="xs">
          <Tooltip label="Refresh triage queue" withArrow>
            <ActionIcon variant="light" color="grape" onClick={() => void refetch()} loading={isFetching}>
              <IconRefresh size={16} />
            </ActionIcon>
          </Tooltip>
        </Group>
      </Group>

      {/* ── KPI Clinical Metrics Strip ───────────────────────── */}
      <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="sm">
        <Card p="sm" bd="1px solid rgba(240, 62, 62, 0.25)">
          <Group justify="space-between">
            <Text size="xs" c="dimmed" fw={600}>
              Pending Senior Review
            </Text>
            <Badge color="red" variant="filled" size="xs">
              SLA Priority
            </Badge>
          </Group>
          <Text fz="xl" fw={700} c="red.4" mt={4}>
            {pendingDecisionCount}
          </Text>
          <Text size="xs" c="dimmed">
            Tier 3 cases awaiting your binding decision
          </Text>
        </Card>

        <Card p="sm">
          <Group justify="space-between">
            <Text size="xs" c="dimmed" fw={600}>
              Average Escalated CRS
            </Text>
            <IconFlame size={16} color="orange" />
          </Group>
          <Text fz="xl" fw={700} c="orange.4" mt={4} ff="monospace">
            {avgCrs}
          </Text>
          <Text size="xs" c="dimmed">
            Cut-off threshold: &gt; 50.0 points
          </Text>
        </Card>

        <Card p="sm">
          <Group justify="space-between">
            <Text size="xs" c="dimmed" fw={600}>
              Resolved & Bound
            </Text>
            <IconCheck size={16} color="teal" />
          </Group>
          <Text fz="xl" fw={700} c="teal.4" mt={4}>
            {decidedCount}
          </Text>
          <Text size="xs" c="dimmed">
            Completed Senior Underwriting sign-offs
          </Text>
        </Card>

        <Card p="sm">
          <Group justify="space-between">
            <Text size="xs" c="dimmed" fw={600}>
              Regulatory Stance
            </Text>
            <IconShieldCheck size={16} color="var(--mantine-color-clinical-3)" />
          </Group>
          <Text fz="sm" fw={600} mt={6}>
            Zero Auto-Rejection
          </Text>
          <Text size="xs" c="dimmed">
            Every elevated case receives human medical oversight
          </Text>
        </Card>
      </SimpleGrid>

      {/* ── Operational Guidance Banner ─────────────────────── */}
      <Alert
        color="grape"
        variant="light"
        icon={<IconStethoscope size={18} />}
        title="Clinical Underwriting Protocol"
      >
        <Text size="xs">
          As Senior Underwriter / Medical Officer, verify the 18 DenseNet vision findings against declared
          symptoms and the Grad-CAM lung heatmap overlay. Underwriters cannot finalize Tier 3 cases without your sign-off.
        </Text>
      </Alert>

      {/* ── Search & Filter Bar ─────────────────────────────── */}
      <Group justify="space-between" align="center">
        <TextInput
          size="xs"
          placeholder="Filter by ref, name, or phone"
          leftSection={<IconSearch size={14} />}
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
          w={280}
        />
        <Text size="xs" c="dimmed">
          Showing {escalatedRows.length} escalated application{escalatedRows.length === 1 ? '' : 's'}
        </Text>
      </Group>

      {error && (
        <Alert color="red" variant="light" icon={<IconAlertCircle size={16} />} title="Could not load escalations">
          {error instanceof Error ? error.message : 'Unknown error'}
        </Alert>
      )}

      {/* ── Triage Table ────────────────────────────────────── */}
      <Box
        style={{
          border: '1px solid var(--mantine-color-default-border)',
          borderRadius: 'var(--mantine-radius-sm)',
          overflow: 'hidden',
        }}
      >
        <Table.ScrollContainer minWidth={780}>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Ref ID</Table.Th>
                <Table.Th>Applicant</Table.Th>
                <Table.Th>Cover Sum</Table.Th>
                <Table.Th>Escalated</Table.Th>
                <Table.Th>Risk Tier</Table.Th>
                <Table.Th>CRS Score</Table.Th>
                <Table.Th>Clinical Status</Table.Th>
                <Table.Th w={140}>Action</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {isPending &&
                [0, 1, 2].map((i) => (
                  <Table.Tr key={i}>
                    <Table.Td colSpan={8}>
                      <Skeleton height={20} />
                    </Table.Td>
                  </Table.Tr>
                ))}

              {!isPending &&
                escalatedRows.map((row) => (
                  <EscalationRow key={row.id} row={row} />
                ))}

              {!isPending && escalatedRows.length === 0 && !error && (
                <Table.Tr>
                  <Table.Td colSpan={8}>
                    <Paper p="xl" style={{ textAlign: 'center', background: 'transparent' }}>
                      <Text fw={600} size="sm" c="teal.4">
                        Escalation Queue Clear
                      </Text>
                      <Text size="xs" c="dimmed" mt={4}>
                        No Tier 3 elevated applications currently require senior adjudication.
                      </Text>
                    </Paper>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Box>
    </Stack>
  )
}

function EscalationRow({ row }: { row: QueueItem }) {
  const isDecided = row.status === 'decided'

  return (
    <Table.Tr style={{ backgroundColor: isDecided ? undefined : 'rgba(240, 62, 62, 0.04)' }}>
      <Table.Td>
        <Text fz="sm" ff="monospace" fw={600}>
          {row.reference}
        </Text>
      </Table.Td>
      <Table.Td fz="sm">{row.applicantName ?? '—'}</Table.Td>
      <Table.Td fz="sm" ff="monospace">
        {row.coverageAmount ? `৳${Math.round(Number(row.coverageAmount)).toLocaleString('en-IN')}` : '—'}
      </Table.Td>
      <Table.Td fz="sm" c="dimmed">
        <Group gap={4} wrap="nowrap">
          <IconClock size={12} />
          <span>{relativeTime(row.submittedAt)}</span>
        </Group>
      </Table.Td>
      <Table.Td>
        <TierBadge tier="elevated" />
      </Table.Td>
      <Table.Td>
        <Badge color="red" variant="filled" size="sm" ff="monospace">
          {row.crs != null ? row.crs.toFixed(1) : '—'}
        </Badge>
      </Table.Td>
      <Table.Td>
        {isDecided ? (
          <Badge color="teal" variant="light" size="sm">
            Adjudicated
          </Badge>
        ) : (
          <Badge color="orange" variant="light" size="sm">
            Awaiting Senior Review
          </Badge>
        )}
      </Table.Td>
      <Table.Td>
        <Button
          component={Link}
          to={`/applications/${row.id}`}
          size="compact-xs"
          variant={isDecided ? 'subtle' : 'filled'}
          color="grape"
          leftSection={<IconEye size={13} />}
        >
          {isDecided ? 'View audit' : 'Adjudicate'}
        </Button>
      </Table.Td>
    </Table.Tr>
  )
}
