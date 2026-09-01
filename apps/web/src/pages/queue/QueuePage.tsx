import {
  ActionIcon,
  Badge,
  Box,
  Group,
  SegmentedControl,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core'
import {
  IconRefresh,
  IconSearch,
  IconVersions,
} from '@tabler/icons-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { AppButton } from '../../components/AppButton'
import { TierBadge, type Tier } from '../../components/TierBadge'

/**
 * Queue (home) — all applications for the current tenant, newest first.
 *
 * Dense underwriting console: a status filter, a free-text search box, a count
 * breakdown, and a table of refs with tier + status chips.
 *
 * TODO: fetch `GET /api/applications?status=&q=&limit=&offset=` and poll with
 * `refetchInterval: 30_000`. Rows below are STUB data so the console renders;
 * replace with the query result.
 */

type ApplicationStatus =
  | 'submitted'
  | 'processing'
  | 'scored'
  | 'insufficient_evidence'
  | 'decided'

const STATUS_META: Record<ApplicationStatus, { label: string; color: string }> = {
  submitted: { label: 'Evaluation pending', color: 'gray' },
  processing: { label: 'Evaluating', color: 'blue' },
  scored: { label: 'Ready for review', color: 'teal' },
  insufficient_evidence: { label: 'More evidence needed', color: 'yellow' },
  decided: { label: 'Decided', color: 'gray' },
}

interface Row {
  id: string
  ref: string
  name: string
  submittedAt: string
  status: ApplicationStatus
  crs: number | null
  tier: Tier | null
}

// Stub data. CRS is 0-100 with tier cut-points at 30 and 65 (app/scoring.py),
// so these values and their tiers must stay consistent — a mismatch here teaches
// the wrong mental model to anyone building against it.
const ROWS: Row[] = [
  { id: 'a1', ref: 'HL-000091', name: 'A. Rahman', submittedAt: ago(2), status: 'scored', crs: 18.4, tier: 'low' },
  { id: 'a2', ref: 'HL-000092', name: 'M. Hossain', submittedAt: ago(9), status: 'processing', crs: null, tier: null },
  { id: 'a3', ref: 'HL-000093', name: 'S. Khatun', submittedAt: ago(31), status: 'scored', crs: 78.2, tier: 'elevated' },
  { id: 'a4', ref: 'HL-000094', name: 'R. Islam', submittedAt: ago(60), status: 'insufficient_evidence', crs: null, tier: 'insufficient_evidence' },
  { id: 'a5', ref: 'HL-000095', name: 'N. Akter', submittedAt: ago(120), status: 'scored', crs: 47.9, tier: 'moderate' },
  { id: 'a6', ref: 'HL-000096', name: 'K. Uddin', submittedAt: ago(300), status: 'submitted', crs: null, tier: null },
  { id: 'a7', ref: 'HL-000097', name: 'J. Choudhury', submittedAt: ago(1440), status: 'decided', crs: 22.7, tier: 'low' },
]

const FILTERS: ({ value: ApplicationStatus | 'all'; label: string })[] = [
  { value: 'all', label: 'All' },
  { value: 'submitted', label: 'Evaluation pending' },
  { value: 'processing', label: 'Evaluating' },
  { value: 'scored', label: 'Ready for review' },
  { value: 'insufficient_evidence', label: 'More evidence needed' },
  { value: 'decided', label: 'Decided' },
]

/** Minutes ago -> ISO, so the stub rows age like real ones. */
function ago(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString()
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
  const [status, setStatus] = useState<ApplicationStatus | 'all'>('all')
  const [query, setQuery] = useState('')
  const [refreshing, setRefreshing] = useState(false)

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return ROWS.filter((r) => {
      if (status !== 'all' && r.status !== status) return false
      if (q && !`${r.ref} ${r.name}`.toLowerCase().includes(q)) return false
      return true
    })
  }, [status, query])

  const counts = useMemo(() => {
    const byStatus: Record<string, number> = {}
    for (const r of ROWS) byStatus[r.status] = (byStatus[r.status] ?? 0) + 1
    return byStatus
  }, [])

  const refresh = () => {
    setRefreshing(true)
    // TODO: refetch query.
    window.setTimeout(() => setRefreshing(false), 600)
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end">
        <div>
          <Text size="sm" fw={600}>
            Review queue
          </Text>
          <Text size="xs" c="dimmed">
            {ROWS.length} applications in scope for this tenant
          </Text>
        </div>
        <AppButton to="/applications/new" icon="plus">
          Review a new client
        </AppButton>
      </Group>

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
        <Spacer />
        <TextInput
          size="xs"
          placeholder="Search ref or name"
          leftSection={<IconSearch size={14} />}
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
          w={220}
        />
        <Tooltip label="Refresh" withArrow>
          <ActionIcon variant="subtle" onClick={refresh} loading={refreshing}>
            <IconRefresh size={16} />
          </ActionIcon>
        </Tooltip>
      </Group>

      <Box style={{ border: '1px solid var(--mantine-color-default-border)', borderRadius: 'var(--mantine-radius-sm)', overflow: 'hidden' }}>
        <Table.ScrollContainer minWidth={760}>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Reference</Table.Th>
                <Table.Th>Applicant</Table.Th>
                <Table.Th>Submitted</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>CRS</Table.Th>
                <Table.Th>Tier</Table.Th>
                <Table.Th w={90}>Action</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((row) => {
                const meta = STATUS_META[row.status]
                return (
                  <Table.Tr key={row.id}>
                    <Table.Td>
                      <Text fz="sm" ff="monospace">
                        {row.ref}
                      </Text>
                    </Table.Td>
                    <Table.Td fz="sm">{row.name}</Table.Td>
                    <Table.Td fz="sm" c="dimmed">
                      {relativeTime(row.submittedAt)}
                    </Table.Td>
                    <Table.Td>
                      <Badge color={meta.color} variant="light" size="sm">
                        {meta.label}
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
                        <TierBadge tier={row.tier} />
                      ) : (
                        <Text fz="sm" c="dimmed">
                          —
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      {row.status === 'scored' ? (
                        <ActionIcon
                          variant="light"
                          color="clinical"
                          component={Link}
                          to={`/applications/${row.id}`}
                          aria-label={`Review ${row.ref}`}
                        >
                          <IconVersions size={16} />
                        </ActionIcon>
                      ) : null}
                    </Table.Td>
                  </Table.Tr>
                )
              })}
              {rows.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={7}>
                    <Text ta="center" c="dimmed" py="lg" size="sm">
                      No applications match the current filter.
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

function Spacer() {
  return <Box style={{ flex: 1 }} />
}
