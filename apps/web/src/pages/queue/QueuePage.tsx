import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Group,
  SegmentedControl,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core'
import {
  IconAlertTriangle,
  IconFlame,
  IconRefresh,
  IconSearch,
  IconShieldCheck,
  IconVersions,
} from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { getQueue, type ApplicationStatus, type QueueItem } from '../../api/client'
import { AppButton } from '../../components/AppButton'
import { TierBadge, type Tier } from '../../components/TierBadge'
import { useAuth } from '../../context/AuthContext'
import type { UserRole } from '../../types/auth'

/**
 * Queue (home) — every application for the signed-in carrier, newest first.
 *
 * Polls every 30 seconds because scoring runs in the background: an application
 * submitted a moment ago arrives here as "Evaluating" and becomes "Ready for
 * review" without anybody reloading the page.
 */

const STATUS_META: Record<ApplicationStatus, { label: string; color: string }> = {
  submitted: { label: 'Evaluation pending', color: 'gray' },
  processing: { label: 'Evaluating', color: 'blue' },
  scored: { label: 'Ready for review', color: 'teal' },
  insufficient_evidence: { label: 'More evidence needed', color: 'yellow' },
  decided: { label: 'Decided', color: 'gray' },
}

const FILTERS: { value: ApplicationStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'submitted', label: 'Evaluation pending' },
  { value: 'processing', label: 'Evaluating' },
  { value: 'scored', label: 'Ready for review' },
  { value: 'insufficient_evidence', label: 'More evidence needed' },
  { value: 'decided', label: 'Decided' },
]

function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

export function QueuePage() {
  const { user } = useAuth()
  const [status, setStatus] = useState<ApplicationStatus | 'all'>('all')
  const [query, setQuery] = useState('')
  const [escalatedOnly, setEscalatedOnly] = useState(false)

  const isSenior = user?.role === 'senior_underwriter'
  const isUnderwriter = user?.role === 'underwriter'

  const { data, isPending, isFetching, error, refetch } = useQuery({
    queryKey: ['applications', status, query],
    queryFn: () => getQueue({ status, q: query }),
    // Scoring finishes in the background, so the row changes under the user.
    refetchInterval: 30_000,
    // Without this the table empties on every keystroke while the next search
    // is in flight, which reads as "no results" rather than "loading".
    placeholderData: keepPreviousData,
  })

  const rawRows = data?.items ?? []
  const counts = data?.counts ?? {}
  const total = data?.total ?? 0

  const elevatedCount = rawRows.filter((r) => r.tier === 'elevated').length
  const rows = escalatedOnly ? rawRows.filter((r) => r.tier === 'elevated') : rawRows

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end">
        <div>
          <Group gap="xs" align="center">
            <Text size="sm" fw={600}>
              Review queue
            </Text>
            {isSenior ? (
              <Badge color="grape" variant="light" size="xs">
                Senior Review & Escalation Workspace
              </Badge>
            ) : isUnderwriter ? (
              <Badge color="clinical" variant="light" size="xs">
                Underwriter Workspace
              </Badge>
            ) : (
              <Badge color="orange" variant="light" size="xs">
                Admin Console
              </Badge>
            )}
          </Group>
          <Text size="xs" c="dimmed">
            {total === 1 ? '1 application' : `${total} applications`} in scope for this carrier
          </Text>
        </div>
        <AppButton to="/applications/new" icon="plus">
          Review a new client
        </AppButton>
      </Group>

      {/* Senior Underwriter Priority Triage Banner */}
      {isSenior && elevatedCount > 0 && (
        <Alert
          color="grape"
          variant="light"
          icon={<IconFlame size={16} />}
          title="Senior Escalation Triage Active"
        >
          <Group justify="space-between" align="center" wrap="wrap" gap="xs">
            <Text size="xs">
              <strong>{elevatedCount}</strong> high-risk (Tier 3 Elevated) application
              {elevatedCount > 1 ? 's' : ''} awaiting mandatory Senior Underwriter clinical review.
            </Text>
            <Button
              size="compact-xs"
              color="grape"
              variant={escalatedOnly ? 'filled' : 'light'}
              onClick={() => setEscalatedOnly(!escalatedOnly)}
            >
              {escalatedOnly ? 'Show all cases' : 'Filter to Escalated cases'}
            </Button>
          </Group>
        </Alert>
      )}

      <Group gap="xs" wrap="nowrap">
        <SegmentedControl
          size="xs"
          value={status}
          onChange={(v) => setStatus(v as ApplicationStatus | 'all')}
          data={FILTERS.map((f) => ({
            value: f.value,
            label: (
              <Group gap={6} wrap="nowrap">
                <span>{f.label}</span>
                {f.value !== 'all' && counts[f.value] != null && (
                  <Badge size="xs" variant="dot" color="gray" circle>
                    {counts[f.value]}
                  </Badge>
                )}
              </Group>
            ),
          }))}
        />
        <Box style={{ flex: 1 }} />
        <TextInput
          size="xs"
          placeholder="Search ref or name"
          leftSection={<IconSearch size={14} />}
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
          w={220}
        />
        <Tooltip label="Refresh" withArrow>
          <ActionIcon variant="subtle" onClick={() => void refetch()} loading={isFetching}>
            <IconRefresh size={16} />
          </ActionIcon>
        </Tooltip>
      </Group>

      {error && (
        <Alert
          color="red"
          variant="light"
          icon={<IconAlertTriangle size={16} />}
          title="Could not load the queue"
        >
          {error instanceof Error ? error.message : 'Unknown error'}
        </Alert>
      )}

      <Box
        style={{
          border: '1px solid var(--mantine-color-default-border)',
          borderRadius: 'var(--mantine-radius-sm)',
          overflow: 'hidden',
        }}
      >
        <Table.ScrollContainer minWidth={760}>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Reference</Table.Th>
                <Table.Th>Applicant</Table.Th>
                <Table.Th>Cover</Table.Th>
                <Table.Th>Submitted</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Risk score</Table.Th>
                <Table.Th>Tier</Table.Th>
                <Table.Th w={90}>Action</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {isPending &&
                [0, 1, 2].map((i) => (
                  <Table.Tr key={`skeleton-${i}`}>
                    <Table.Td colSpan={8}>
                      <Skeleton height={18} />
                    </Table.Td>
                  </Table.Tr>
                ))}

              {!isPending && rows.map((row) => <Row key={row.id} row={row} userRole={user?.role} />)}

              {!isPending && rows.length === 0 && !error && (
                <Table.Tr>
                  <Table.Td colSpan={8}>
                    <Text ta="center" c="dimmed" py="lg" size="sm">
                      {total === 0
                        ? 'No applications yet. Start by reviewing a new client.'
                        : 'No applications match the current filter.'}
                    </Text>
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

function Row({ row, userRole }: { row: QueueItem; userRole?: UserRole }) {
  const meta = STATUS_META[row.status]
  // Anything already evaluated is worth opening — including an application that
  // could not be scored, because that screen explains why.
  const openable = row.status === 'scored' || row.status === 'decided' ||
    row.status === 'insufficient_evidence'
  const isElevated = row.tier === 'elevated'
  const isSenior = userRole === 'senior_underwriter'
  const isUnderwriter = userRole === 'underwriter'

  return (
    <Table.Tr
      style={
        isElevated && isSenior
          ? { backgroundColor: 'rgba(174, 62, 201, 0.06)' }
          : undefined
      }
    >
      <Table.Td>
        <Group gap={6} wrap="nowrap">
          <Text fz="sm" ff="monospace">
            {row.reference}
          </Text>
          {isElevated && (
            <Tooltip
              label={
                isUnderwriter
                  ? 'Elevated risk — mandatory senior underwriter escalation'
                  : 'Mandatory Senior Review case'
              }
              withArrow
            >
              <Badge size="xs" variant="filled" color="red">
                Tier 3
              </Badge>
            </Tooltip>
          )}
        </Group>
      </Table.Td>
      <Table.Td fz="sm">{row.applicantName ?? '—'}</Table.Td>
      <Table.Td fz="sm" ff="monospace">
        {/* How much is at stake, so triage is not done on risk alone. */}
        {row.coverageAmount ? `৳${Math.round(Number(row.coverageAmount)).toLocaleString('en-IN')}` : '—'}
      </Table.Td>
      <Table.Td fz="sm" c="dimmed">
        {relativeTime(row.submittedAt)}
      </Table.Td>
      <Table.Td>
        <Badge color={meta?.color ?? 'gray'} variant="light" size="sm">
          {meta?.label ?? row.status}
        </Badge>
      </Table.Td>
      <Table.Td>
        {row.crs != null ? (
          <Text fz="sm" ff="monospace">
            {row.crs.toFixed(1)}
          </Text>
        ) : (
          <Text fz="sm" c="dimmed">
            —
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        {row.tier ? (
          <TierBadge tier={row.tier as Tier} />
        ) : (
          <Text fz="sm" c="dimmed">
            —
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        {openable ? (
          <Tooltip
            label={
              isElevated && isSenior
                ? `Senior Review for ${row.reference}`
                : isElevated && isUnderwriter
                ? `Review ${row.reference} (Escalation required)`
                : `Review ${row.reference}`
            }
            withArrow
          >
            <ActionIcon
              variant="light"
              color={isElevated && isSenior ? 'grape' : 'clinical'}
              component={Link}
              to={`/applications/${row.id}`}
              aria-label={`Review ${row.reference}`}
            >
              {isElevated && isSenior ? (
                <IconShieldCheck size={16} />
              ) : (
                <IconVersions size={16} />
              )}
            </ActionIcon>
          </Tooltip>
        ) : null}
      </Table.Td>
    </Table.Tr>
  )
}
