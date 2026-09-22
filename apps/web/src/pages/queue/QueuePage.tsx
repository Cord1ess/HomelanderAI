import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Group,
  SegmentedControl,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core'
import {
  IconArrowRight,
  IconFlame,
  IconInfoCircle,
  IconPlus,
  IconRefresh,
  IconSearch,
} from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { getQueue, type ApplicationStatus, type QueueItem } from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { Stat } from '../../components/Stat'
import { StatusBadge } from '../../components/StatusBadge'
import { EmptyState, ErrorState } from '../../components/states'
import { TierBadge, type Tier } from '../../components/TierBadge'
import { useAuth } from '../../context/AuthContext'
import { STATUS_META, STATUS_ORDER } from '../../status'
import type { UserRole } from '../../types/auth'

/**
 * Applications: every one the signed-in company has taken, newest first.
 *
 * Polls every 30 seconds because scoring runs in the background: an application
 * submitted a moment ago arrives here as "Reading evidence" and becomes "Ready
 * to decide" without anybody reloading. A row whose status changed since the
 * last poll flashes once, so the change is seen rather than discovered.
 */

const FILTERS: { value: ApplicationStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  ...STATUS_ORDER.map((value) => ({ value, label: STATUS_META[value].label })),
]

/** "Tue 29 Sep": a date, deliberately not a countdown. */
function formatDay(isoDate: string): string {
  // Parsed as local midnight, not UTC: a bare date given a "Z" would show as
  // the previous day for anyone east of Greenwich.
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
}

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

function formatTaka(value: string | number): string {
  return `৳${Math.round(Number(value)).toLocaleString('en-IN')}`
}

/**
 * Which rows changed since the last poll, by id.
 *
 * The first load flashes nothing: everything is new to the screen, not new to
 * the world. After that, a row flashes when it appears or when its status
 * moves, which is exactly the two things worth noticing.
 *
 * The comparison is against the previous *data*, not the previous render, so
 * the flagged set holds until the next poll and the animation gets to finish.
 * (React Query keeps the same array reference while the data is unchanged.)
 */
function useChangedRows(rows: QueueItem[] | undefined): Set<string> {
  const [memo, setMemo] = useState<{
    rows: QueueItem[]
    seen: Map<string, ApplicationStatus>
    changed: Set<string>
  } | null>(null)

  if (rows && memo?.rows !== rows) {
    const changed = new Set<string>()
    if (memo) {
      for (const row of rows) {
        if (memo.seen.get(row.id) !== row.status) changed.add(row.id)
      }
    }
    setMemo({ rows, seen: new Map(rows.map((r) => [r.id, r.status])), changed })
  }
  return memo?.changed ?? EMPTY
}

const EMPTY: Set<string> = new Set()

export function QueuePage() {
  const { user } = useAuth()
  const [status, setStatus] = useState<ApplicationStatus | 'all'>('all')
  const [query, setQuery] = useState('')
  const [escalatedOnly, setEscalatedOnly] = useState(false)

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
  const changed = useChangedRows(data?.items)

  const isMedical = user?.role === 'medical_professional'

  const decidedCount = rawRows.filter((r) => r.status === 'decided').length
  const pendingCount = rawRows.filter((r) => r.status !== 'decided').length
  const readingCount = rawRows.filter((r) => r.status === 'processing').length

  return (
    <Stack gap="md">
      <PageHeader
        screen="queue"
        actions={
          <>
            <Button component={Link} to="/applications/new" size="xs" leftSection={<IconPlus size={14} />}>
              New application
            </Button>
            {isMedical && (
              <Button
                component={Link}
                to="/escalations"
                color="grape"
                size="xs"
                variant="light"
                leftSection={<IconFlame size={14} />}
              >
                Escalations
              </Button>
            )}
          </>
        }
      >
        {/* Four real counts, the same for every role. */}
        <SimpleGrid cols={{ base: 2, md: 4 }} spacing="xs">
          <Stat label="Applications" value={total} hint="Everything your company has taken" />
          <Stat
            label="Waiting for a decision"
            value={pendingCount}
            color="orange"
            hint={readingCount > 0 ? `${readingCount} being read right now` : undefined}
          />
          <Stat
            label="Elevated risk"
            value={elevatedCount}
            color="red"
            hint={isMedical ? 'Waiting for your decision' : 'Need a medical professional'}
          />
          <Stat label="Decided" value={decidedCount} color="teal" />
        </SimpleGrid>
      </PageHeader>

      {/* The medical professional's own work, called out above the list. */}
      {isMedical && elevatedCount > 0 && (
        <Alert color="grape" variant="light" icon={<IconFlame size={16} />} title="Waiting for a medical decision">
          <Group justify="space-between" align="center" wrap="wrap" gap="xs">
            <Text size="xs">
              <strong>{elevatedCount}</strong> application{elevatedCount > 1 ? 's are' : ' is'} at elevated
              risk and can only be decided by a medical professional.
            </Text>
            <Button
              size="compact-xs"
              color="grape"
              variant={escalatedOnly ? 'filled' : 'light'}
              onClick={() => setEscalatedOnly(!escalatedOnly)}
            >
              {escalatedOnly ? 'Show all applications' : 'Show only these'}
            </Button>
          </Group>
        </Alert>
      )}

      <Group gap="xs" wrap="wrap">
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
          placeholder="Search by reference or name"
          aria-label="Search applications"
          leftSection={<IconSearch size={14} />}
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
          w={240}
        />
        <Tooltip label="Check for changes now" withArrow>
          <ActionIcon variant="subtle" aria-label="Refresh" onClick={() => void refetch()} loading={isFetching}>
            <IconRefresh size={16} />
          </ActionIcon>
        </Tooltip>
      </Group>

      {error && !data && (
        <ErrorState title="Could not load the applications" error={error} retry={() => void refetch()} />
      )}

      {!(error && !data) && (
        <Box
          style={{
            border: '1px solid var(--neo-border-mid)',
            borderRadius: 'var(--mantine-radius-sm)',
            overflow: 'hidden',
          }}
        >
          <Table.ScrollContainer minWidth={820}>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Reference</Table.Th>
                  <Table.Th>Client</Table.Th>
                  <Table.Th>Cover</Table.Th>
                  <Table.Th>Submitted</Table.Th>
                  <Table.Th>Answer promised</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>
                    <Group gap={4} wrap="nowrap">
                      Score
                      <Tooltip
                        label="The models' composite risk score, 0 to 100. Advice for the person deciding, never a decision."
                        withArrow
                        multiline
                        maw={260}
                      >
                        <IconInfoCircle size={13} style={{ color: 'var(--neo-muted)' }} />
                      </Tooltip>
                    </Group>
                  </Table.Th>
                  <Table.Th>Tier</Table.Th>
                  <Table.Th w={56} aria-label="Open" />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {isPending &&
                  [0, 1, 2].map((i) => (
                    <Table.Tr key={`skeleton-${i}`}>
                      <Table.Td colSpan={9}>
                        <Skeleton height={18} />
                      </Table.Td>
                    </Table.Tr>
                  ))}

                {!isPending &&
                  rows.map((row) => (
                    <Row key={row.id} row={row} userRole={user?.role} changed={changed.has(row.id)} />
                  ))}

                {!isPending && rows.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={9} p={0}>
                      {total === 0 ? (
                        <EmptyState
                          title="No applications yet"
                          text="Take the first one and it will appear here. The models read the evidence in the background and the row updates on its own."
                          action={
                            <Button component={Link} to="/applications/new" size="xs" leftSection={<IconPlus size={14} />}>
                              New application
                            </Button>
                          }
                        />
                      ) : (
                        <EmptyState
                          title="Nothing matches"
                          text={
                            escalatedOnly
                              ? 'No application at elevated risk matches this filter.'
                              : 'No application has this status, or none matches the search.'
                          }
                        />
                      )}
                    </Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Box>
      )}

      <Text size="xs" style={{ color: 'var(--neo-muted)' }}>
        Scores and tiers are the models' advice. A person records every decision, under their own name.
      </Text>
    </Stack>
  )
}

function Row({ row, userRole, changed }: { row: QueueItem; userRole?: UserRole; changed: boolean }) {
  const navigate = useNavigate()
  // Anything already evaluated is worth opening, including an application that
  // could not be scored, because that screen explains why.
  const openable =
    row.status === 'scored' ||
    row.status === 'decided' ||
    row.status === 'insufficient_evidence' ||
    row.status === 'awaiting_evidence' ||
    row.status === 'escalated'
  const isElevated = row.tier === 'elevated'
  const isMedical = userRole === 'medical_professional'
  const isUnderwriter = userRole === 'underwriter'
  const href = `/applications/${row.id}`

  return (
    <Table.Tr
      className="queue-row"
      data-changed={changed || undefined}
      data-openable={openable || undefined}
      onClick={openable ? () => navigate(href) : undefined}
      style={
        isElevated && isMedical
          ? { backgroundColor: 'color-mix(in srgb, var(--mantine-color-grape-6) 8%, transparent)' }
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
                  ? 'Elevated risk. You can escalate this, not approve it.'
                  : 'Elevated risk. Needs a medical professional to decide.'
              }
              withArrow
              multiline
              maw={240}
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
        {row.coverageAmount ? formatTaka(row.coverageAmount) : '—'}
      </Table.Td>
      <Table.Td fz="sm" style={{ color: 'var(--neo-muted)' }}>
        {relativeTime(row.submittedAt)}
      </Table.Td>
      {/* The date the client was given. Red once it has passed while the
          company still holds the case; not while waiting on the client, whose
          delay it would be. */}
      <Table.Td fz="sm" style={{ color: row.overdue ? 'var(--neo-danger)' : 'var(--neo-muted)' }}>
        {row.expectedBy ? formatDay(row.expectedBy) : '—'}
        {row.overdue && (
          <Tooltip label="The date promised to the client has passed" withArrow>
            <Badge ml={6} size="xs" color="red" variant="light">
              Late
            </Badge>
          </Tooltip>
        )}
      </Table.Td>
      <Table.Td>
        <StatusBadge status={row.status} />
      </Table.Td>
      <Table.Td>
        {row.crs != null ? (
          <Text fz="sm" ff="monospace">
            {row.crs.toFixed(1)}
          </Text>
        ) : (
          <Text fz="sm" style={{ color: 'var(--neo-muted)' }}>
            —
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        {row.tier ? (
          <TierBadge tier={row.tier as Tier} />
        ) : (
          <Text fz="sm" style={{ color: 'var(--neo-muted)' }}>
            —
          </Text>
        )}
      </Table.Td>
      <Table.Td onClick={(e) => e.stopPropagation()}>
        {openable ? (
          <Tooltip label={`Open ${row.reference}`} withArrow>
            <ActionIcon
              variant="light"
              color={isElevated && isMedical ? 'grape' : 'clinical'}
              component={Link}
              to={href}
              aria-label={`Open ${row.reference}`}
            >
              <IconArrowRight size={16} />
            </ActionIcon>
          </Tooltip>
        ) : (
          <Tooltip label="Opens once the models have finished reading" withArrow>
            <ActionIcon variant="subtle" disabled aria-label="Not ready yet">
              <IconArrowRight size={16} />
            </ActionIcon>
          </Tooltip>
        )}
      </Table.Td>
    </Table.Tr>
  )
}
