import {
  Badge,
  Button,
  Card,
  Container,
  Group,
  SegmentedControl,
  Stack,
  Table,
  Text,
} from '@mantine/core'
import { IconPlus } from '@tabler/icons-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

/**
 * Queue (home) — all applications for the current tenant, newest first.
 *
 * Filtered by status, polled with TanStack Query `refetchInterval: 30_000`.
 * The "Review a new client" button is the single most-used control in the
 * product — top right, primary colour.
 *
 * TODO: fetch `GET /api/applications?status=&limit=&offset=`; map DB status →
 * badge wording/colour per the spec table; relative "Submitted" time.
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

const FILTERS: ({ value: ApplicationStatus | 'all'; label: string })[] = [
  { value: 'all', label: 'All' },
  { value: 'submitted', label: 'Evaluation pending' },
  { value: 'processing', label: 'Evaluating' },
  { value: 'scored', label: 'Ready for review' },
  { value: 'insufficient_evidence', label: 'More evidence needed' },
  { value: 'decided', label: 'Decided' },
]

interface Row {
  ref: string
  submitted: string
  status: ApplicationStatus
  risk: { crs?: number; tier?: string } | null
}

const ROWS: Row[] = [] // TODO: from useQuery keyed ['applications', status]

export function QueuePage() {
  const [status, setStatus] = useState<ApplicationStatus | 'all'>('all')

  return (
    <Container size="lg">
      <Stack gap="md">
        <Group justify="space-between">
          <div>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: '0.12em' }}>
              Queue
            </Text>
            <Text size="sm" c="dimmed">
              {/* {ROWS.length} */} Applications
            </Text>
          </div>
          <Button component={Link} to="/applications/new" leftSection={<IconPlus size={16} />}>
            Review a new client
          </Button>
        </Group>

        <SegmentedControl
          value={status}
          onChange={(v) => setStatus(v as ApplicationStatus | 'all')}
          data={FILTERS.map((f) => ({ value: f.value, label: f.label }))}
        />

        <Card padding={0}>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Reference</Table.Th>
                <Table.Th>Submitted</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Risk</Table.Th>
                <Table.Th>Action</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {ROWS.map((row) => {
                const meta = STATUS_META[row.status]
                return (
                  <Table.Tr key={row.ref}>
                    <Table.Td ff="monospace">{row.ref}</Table.Td>
                    <Table.Td>{row.submitted}</Table.Td>
                    <Table.Td>
                      <Badge color={meta.color}>{meta.label}</Badge>
                    </Table.Td>
                    <Table.Td>
                      {row.risk?.crs != null ? (
                        <Group gap="xs">
                          <Text size="sm">{row.risk.crs}</Text>
                          <Badge color={row.risk.tier}>{row.risk.tier}</Badge>
                        </Group>
                      ) : (
                        <Text c="dimmed">—</Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      {row.status === 'scored' ? (
                        <Button size="xs" variant="light" component={Link} to={`/applications/${row.ref}`}>
                          Review
                        </Button>
                      ) : null}
                    </Table.Td>
                  </Table.Tr>
                )
              })}
              {ROWS.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={5}>
                    <Text ta="center" c="dimmed" py="lg" size="sm">
                      No applications yet. Link the queue query to populate this table.
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Card>
      </Stack>
    </Container>
  )
}
