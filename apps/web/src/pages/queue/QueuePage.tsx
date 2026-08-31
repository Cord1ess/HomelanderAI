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
import { TierBadge } from '../../components/TierBadge'

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

type Tier = 'low' | 'moderate' | 'elevated' | 'insufficient'

interface Row {
  id: string
  ref: string
  name: string
  submittedIn: string
  status: ApplicationStatus
  crs: number | null
  tier: Tier | null
}

const ROWS: Row[] = [
  { id: 'a1', ref: 'APP-2026-0091', name: 'A. Rahman', submittedIn: '2 m ago', status: 'scored', crs: 2.1, tier: 'low' },
  { id: 'a2', ref: 'APP-2026-0092', name: 'M. Hossain', submittedIn: '9 m ago', status: 'processing', crs: null, tier: null },
  { id: 'a3', ref: 'APP-2026-0093', name: 'S. Khatun', submittedIn: '31 m ago', status: 'scored', crs: 5.8, tier: 'elevated' },
  { id: 'a4', ref: 'APP-2026-0094', name: 'R. Islam', submittedIn: '1 h ago', status: 'insufficient_evidence', crs: null, tier: 'insufficient' },
  { id: 'a5', ref: 'APP-2026-0095', name: 'N. Akter', submittedIn: '2 h ago', status: 'scored', crs: 3.4, tier: 'moderate' },
  { id: 'a6', ref: 'APP-2026-0096', name: 'K. Uddin', submittedIn: '5 h ago', status: 'submitted', crs: null, tier: null },
  { id: 'a7', ref: 'APP-2026-0097', name: 'J. Choudhury', submittedIn: '1 d ago', status: 'decided', crs: 2.6, tier: 'low' },
]

const FILTERS: ({ value: ApplicationStatus | 'all'; label: string })[] = [
  { value: 'all', label: 'All' },
  { value: 'submitted', label: 'Evaluation pending' },
  { value: 'processing', label: 'Evaluating' },
  { value: 'scored', label: 'Ready for review' },
  { value: 'insufficient_evidence', label: 'More evidence needed' },
  { value: 'decided', label: 'Decided' },
]

function relativeTime(v: string): string {
  return v
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
                      {relativeTime(row.submittedIn)}
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
