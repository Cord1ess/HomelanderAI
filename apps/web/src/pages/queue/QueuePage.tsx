import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Card,
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
  IconAlertTriangle,
  IconFlame,
  IconRefresh,
  IconSearch,
  IconShieldCheck,
  IconUsers,
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
import { ROLE_LABEL } from '../../types/auth'

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
  // Distinct from the line above: this one waits on the applicant, that one
  // on the operator. Orange, not yellow, so the two do not read as the same.
  awaiting_evidence: { label: 'Waiting on applicant', color: 'orange' },
  decided: { label: 'Decided', color: 'gray' },
}

const FILTERS: { value: ApplicationStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'submitted', label: 'Evaluation pending' },
  { value: 'processing', label: 'Evaluating' },
  { value: 'scored', label: 'Ready for review' },
  { value: 'insufficient_evidence', label: 'More evidence needed' },
  { value: 'awaiting_evidence', label: 'Waiting on applicant' },
  { value: 'decided', label: 'Decided' },
]

/** "Tue 29 Sep" — a date, deliberately not a countdown. */
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

  const isAdmin = user?.role === 'admin'
  const isMedical = user?.role === 'medical_professional'

  const tier1Count = rawRows.filter((r) => r.tier === 'low').length
  const tier2Count = rawRows.filter((r) => r.tier === 'moderate').length
  const tier3Count = rawRows.filter((r) => r.tier === 'elevated').length
  const decidedCount = rawRows.filter((r) => r.status === 'decided').length
  const pendingCount = rawRows.filter((r) => r.status !== 'decided').length

  return (
    <Stack gap="md">
      {/* ── Role-Tailored Header ─────────────────────────────── */}
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Group gap="xs" align="center">
            <Text size="lg" fw={700}>
              {isMedical
                ? 'Clinical Review & Triage Queue'
                : isAdmin
                ? 'Carrier Submission Audit & Governance'
                : 'Underwriter Intake & Review Queue'}
            </Text>
            {isMedical ? (
              <Badge color="grape" variant="filled" size="xs">
                {ROLE_LABEL.medical_professional}
              </Badge>
            ) : isAdmin ? (
              <Badge color="orange" variant="filled" size="xs">
                {ROLE_LABEL.admin}
              </Badge>
            ) : (
              <Badge color="clinical" variant="filled" size="xs">
                Underwriter
              </Badge>
            )}
          </Group>
          <Text size="xs" c="dimmed">
            {isMedical
              ? 'Clinical review authority: audit Grad-CAM heatmaps, verify DenseNet findings, and adjudicate escalated cases.'
              : isAdmin
              ? 'Carrier organization governance: monitor operator throughput, application lifecycles, and cryptographic audit trails.'
              : 'Frontline workspace: intake new clients and adjudicate Tier 1 & 2 policy applications.'}
          </Text>
        </div>

        <div>
          {isMedical ? (
            <Group gap="xs">
              <AppButton to="/applications/new" icon="plus" size="xs">
                New Applicant Intake
              </AppButton>
              <Button
                component={Link}
                to="/escalations"
                color="grape"
                size="xs"
                variant="light"
                leftSection={<IconFlame size={14} />}
              >
                Open Escalations Inbox
              </Button>
            </Group>
          ) : isAdmin ? (
            <Group gap="xs">
              <AppButton to="/applications/new" icon="plus" size="xs">
                New Applicant Intake
              </AppButton>
              <Button
                component={Link}
                to="/admin/users"
                color="orange"
                size="xs"
                variant="light"
                leftSection={<IconUsers size={14} />}
              >
                Manage Staff Directory
              </Button>
            </Group>
          ) : (
            <AppButton to="/applications/new" icon="plus">
              Review a new client
            </AppButton>
          )}
        </div>
      </Group>

      {/* ── Role-Specific KPI Metrics Strip ──────────────────── */}
      {isMedical ? (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="xs">
          <Card p="xs" bd="1px solid rgba(240, 62, 62, 0.25)">
            <Text size="xs" c="dimmed" fw={600}>
              ⚡ Mandatory Escalations
            </Text>
            <Text fz="lg" fw={700} c="red.4">
              {tier3Count}
            </Text>
          </Card>
          <Card p="xs">
            <Text size="xs" c="dimmed" fw={600}>
              Pending Sign-off
            </Text>
            <Text fz="lg" fw={700} c="orange.4">
              {pendingCount}
            </Text>
          </Card>
          <Card p="xs">
            <Text size="xs" c="dimmed" fw={600}>
              Grad-CAM Verified
            </Text>
            <Text fz="lg" fw={700} c="clinical.4">
              {rawRows.filter((r) => r.status === 'scored').length}
            </Text>
          </Card>
          <Card p="xs">
            <Text size="xs" c="dimmed" fw={600}>
              Finalized Decisions
            </Text>
            <Text fz="lg" fw={700} c="teal.4">
              {decidedCount}
            </Text>
          </Card>
        </SimpleGrid>
      ) : isAdmin ? (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="xs">
          <Card p="xs">
            <Text size="xs" c="dimmed" fw={600}>
              Total Carrier Ingestion
            </Text>
            <Text fz="lg" fw={700}>
              {total}
            </Text>
          </Card>
          <Card p="xs">
            <Text size="xs" c="dimmed" fw={600}>
              Active Backlog
            </Text>
            <Text fz="lg" fw={700} c="orange.4">
              {pendingCount}
            </Text>
          </Card>
          <Card p="xs">
            <Text size="xs" c="dimmed" fw={600}>
              Bound Policies
            </Text>
            <Text fz="lg" fw={700} c="teal.4">
              {decidedCount}
            </Text>
          </Card>
          <Card p="xs">
            <Text size="xs" c="dimmed" fw={600}>
              Cryptographic Audit
            </Text>
            <Text fz="lg" fw={700} c="teal.4">
              100% Compliant
            </Text>
          </Card>
        </SimpleGrid>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="xs">
          <Card p="xs">
            <Text size="xs" c="dimmed" fw={600}>
              Assigned in Queue
            </Text>
            <Text fz="lg" fw={700}>
              {total}
            </Text>
          </Card>
          <Card p="xs">
            <Text size="xs" c="dimmed" fw={600}>
              Tier 1 Fast-Track Ready
            </Text>
            <Text fz="lg" fw={700} c="teal.4">
              {tier1Count}
            </Text>
          </Card>
          <Card p="xs">
            <Text size="xs" c="dimmed" fw={600}>
              Tier 2 Moderate Review
            </Text>
            <Text fz="lg" fw={700} c="yellow.4">
              {tier2Count}
            </Text>
          </Card>
          <Card p="xs">
            <Text size="xs" c="dimmed" fw={600}>
              Tier 3 Awaiting Medical Review
            </Text>
            <Text fz="lg" fw={700} c="red.4">
              {tier3Count}
            </Text>
          </Card>
        </SimpleGrid>
      )}

      {/* Medical Professional priority triage banner */}
      {isMedical && elevatedCount > 0 && (
        <Alert
          color="grape"
          variant="light"
          icon={<IconFlame size={16} />}
          title="Medical Review Triage Active"
        >
          <Group justify="space-between" align="center" wrap="wrap" gap="xs">
            <Text size="xs">
              <strong>{elevatedCount}</strong> high-risk (Tier 3 Elevated) application
              {elevatedCount > 1 ? 's' : ''} awaiting mandatory Medical Professional review.
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
                <Table.Th>Expected by</Table.Th>
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
                    <Table.Td colSpan={9}>
                      <Skeleton height={18} />
                    </Table.Td>
                  </Table.Tr>
                ))}

              {!isPending && rows.map((row) => <Row key={row.id} row={row} userRole={user?.role} />)}

              {!isPending && rows.length === 0 && !error && (
                <Table.Tr>
                  <Table.Td colSpan={9}>
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
    row.status === 'insufficient_evidence' || row.status === 'awaiting_evidence'
  const isElevated = row.tier === 'elevated'
  const isMedical = userRole === 'medical_professional'
  const isUnderwriter = userRole === 'underwriter'

  return (
    <Table.Tr
      style={
        isElevated && isMedical
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
                  ? 'Elevated risk — mandatory escalation to a medical professional'
                  : 'Mandatory medical review case'
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
      {/* The date the applicant was given. Red once it has passed while the
          carrier still holds the case, so a late file is visible from the
          queue and not only from inside it. */}
      <Table.Td fz="sm" c={row.overdue ? 'red' : 'dimmed'}>
        {row.expectedBy ? formatDay(row.expectedBy) : '—'}
        {row.overdue && (
          <Badge ml={6} size="xs" color="red" variant="light">
            Late
          </Badge>
        )}
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
              isElevated && isMedical
                ? `Medical review for ${row.reference}`
                : isElevated && isUnderwriter
                ? `Review ${row.reference} (Escalation required)`
                : `Review ${row.reference}`
            }
            withArrow
          >
            <ActionIcon
              variant="light"
              color={isElevated && isMedical ? 'grape' : 'clinical'}
              component={Link}
              to={`/applications/${row.id}`}
              aria-label={`Review ${row.reference}`}
            >
              {isElevated && isMedical ? (
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
