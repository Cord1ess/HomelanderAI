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
import { DoctorVerdictBadge } from '../../components/DoctorVerdictBadge'
import { PageHeader } from '../../components/PageHeader'
import { Stat } from '../../components/Stat'
import { TierBadge, type Tier } from '../../components/TierBadge'

/**
 * Doctor reviews: the applications underwriters have sent to a doctor.
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
  // Everything sent to a doctor: waiting now, or sent back with a verdict. For
  // a doctor the API returns nothing else; an administrator sees the whole
  // queue, so it is narrowed here the same way.
  const allItems = data?.items ?? []
  const escalatedRows = allItems
    .filter((item) => item.status === 'escalated' || Boolean(item.doctorVerdict))
    .sort((a, b) => Number(b.status === 'escalated') - Number(a.status === 'escalated'))

  const pendingDecisionCount = escalatedRows.filter((item) => item.status === 'escalated').length
  const correctCount = escalatedRows.filter((item) => item.doctorVerdict === 'accurate').length
  const wrongCount = escalatedRows.filter((item) => item.doctorVerdict === 'inaccurate').length

  return (
    <Stack gap="md">
      <PageHeader
        screen="escalations"
        actions={
          <Tooltip label="Check for new cases" withArrow>
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
            label="Waiting for your review"
            value={pendingDecisionCount}
            color="red"
            hint="Check the results and send them back to the underwriter."
          />
          <Stat label="Sent back as correct" value={correctCount} color="teal" hint="Results verified" />
          <Stat label="Sent back as wrong" value={wrongCount} color="orange" hint="Results corrected" />
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
          {escalatedRows.length} application{escalatedRows.length === 1 ? '' : 's'} sent to a doctor
        </Text>
      </Group>

      {error && (
        <Alert color="red" variant="light" icon={<IconAlertCircle size={16} />} title="Could not load doctor reviews">
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
                <Table.Th>Sent</Table.Th>
                <Table.Th>Risk Tier</Table.Th>
                <Table.Th>CRS Score</Table.Th>
                <Table.Th>Your review</Table.Th>
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
                        Nothing waiting for you
                      </Text>
                      <Text size="xs" c="dimmed" mt={4}>
                        Applications an underwriter sends to a doctor appear here.
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
  const waiting = row.status === 'escalated'

  return (
    <Table.Tr style={{ backgroundColor: waiting ? 'var(--neo-danger-soft)' : undefined }}>
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
      <Table.Td>{row.tier ? <TierBadge tier={row.tier as Tier} /> : '—'}</Table.Td>
      <Table.Td>
        <Text fz="sm" ff="monospace" fw={600}>
          {row.crs != null ? row.crs.toFixed(1) : '—'}
        </Text>
      </Table.Td>
      <Table.Td>
        {waiting ? (
          <Badge color="orange" variant="light" size="sm">
            Waiting for your review
          </Badge>
        ) : (
          <DoctorVerdictBadge verdict={row.doctorVerdict} />
        )}
      </Table.Td>
      <Table.Td>
        <Button
          component={Link}
          to={`/applications/${row.id}`}
          size="compact-xs"
          variant={waiting ? 'filled' : 'subtle'}
          color="grape"
          leftSection={<IconEye size={13} />}
        >
          {waiting ? 'Review' : 'Open'}
        </Button>
      </Table.Td>
    </Table.Tr>
  )
}
