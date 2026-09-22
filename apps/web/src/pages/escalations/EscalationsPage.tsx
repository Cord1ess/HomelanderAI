import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
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
  IconClock,
  IconEye,
  IconRefresh,
  IconSearch,
} from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { getQueue, type QueueItem } from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { Stat } from '../../components/Stat'
import { TierBadge } from '../../components/TierBadge'

/**
 * Medical Professional Escalations Command Center.
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

  // The API decides the tier, with the carrier's thresholds. This screen used
  // to add its own rule (score above 45), which put applications here that the
  // system had not escalated and labelled the cut-off with a number that was
  // never the real one.
  const allItems = data?.items ?? []
  const escalatedRows = allItems.filter(
    (item) => item.status === 'escalated' || item.tier === 'elevated',
  )

  const pendingDecisionCount = escalatedRows.filter((item) => item.status !== 'decided').length
  const decidedCount = escalatedRows.filter((item) => item.status === 'decided').length
  const waiting = escalatedRows.filter((item) => item.status !== 'decided')
  const avgCrs =
    waiting.length > 0
      ? (waiting.reduce((acc, curr) => acc + (curr.crs ?? 0), 0) / waiting.length).toFixed(1)
      : '—'

  return (
    <Stack gap="md">
      <PageHeader
        screen="escalations"
        actions={
          <Tooltip label="Check for new escalations" withArrow>
            <ActionIcon
              variant="light"
              color="grape"
              aria-label="Refresh"
              onClick={() => void refetch()}
              loading={isFetching}
            >
              <IconRefresh size={16} />
            </ActionIcon>
          </Tooltip>
        }
      >
        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="xs">
          <Stat
            label="Waiting for your decision"
            value={pendingDecisionCount}
            color="red"
            hint="Elevated risk. An underwriter cannot decide these."
          />
          <Stat label="Average score of those waiting" value={avgCrs} color="orange" hint="Out of 100" />
          <Stat label="Decided" value={decidedCount} color="teal" hint="Escalations already closed" />
        </SimpleGrid>
      </PageHeader>

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
        <Text size="xs" style={{ color: 'var(--neo-muted)' }}>
          {escalatedRows.length} escalated application{escalatedRows.length === 1 ? '' : 's'}
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
                        No Tier 3 elevated applications currently require medical review.
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
    <Table.Tr style={{ backgroundColor: isDecided ? undefined : 'var(--neo-danger-soft)' }}>
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
            Decided
          </Badge>
        ) : (
          <Badge color="orange" variant="light" size="sm">
            Waiting for your decision
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
          {isDecided ? 'Open' : 'Decide'}
        </Button>
      </Table.Td>
    </Table.Tr>
  )
}
