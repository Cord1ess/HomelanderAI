import { Anchor, Badge, Box, Button, Group, SegmentedControl, Stack, Table, Text } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconCheck, IconX } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { type AccessRequest, decideAccessRequest, getAccessRequests } from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { Stat } from '../../components/Stat'
import { EmptyState, ErrorState, LoadingState } from '../../components/states'

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })

/**
 * The owner's inbox of requests to see a client's personal details. Each one
 * says who asked, about whom, and why; approving opens that one client to
 * that one person for a day.
 */
export function AccessRequestsPage() {
  const [show, setShow] = useState<'pending' | 'all'>('pending')
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['access-requests'],
    queryFn: getAccessRequests,
    refetchInterval: 30_000,
  })
  const all = data ?? []
  const waiting = all.filter((r) => r.status === 'pending')
  const rows = show === 'pending' ? waiting : all

  return (
    <Stack gap="md">
      <PageHeader screen="access">
        <Group gap="xs" grow>
          <Stat label="Waiting for you" value={waiting.length} color="red" hint="Approve or decline" />
          <Stat
            label="Approved"
            value={all.filter((r) => r.status === 'approved').length}
            color="teal"
            hint="Each for one day"
          />
          <Stat
            label="Declined"
            value={all.filter((r) => r.status === 'declined').length}
            color="gray"
          />
        </Group>
      </PageHeader>

      <SegmentedControl
        size="xs"
        w={260}
        value={show}
        onChange={(v) => setShow(v as 'pending' | 'all')}
        data={[
          { value: 'pending', label: `Waiting (${waiting.length})` },
          { value: 'all', label: `All (${all.length})` },
        ]}
      />

      {isPending && <LoadingState label="Loading requests" />}
      {error && !data && (
        <ErrorState title="Could not load the requests" error={error} retry={() => void refetch()} />
      )}

      {data && (
        <Box
          style={{
            border: '1px solid var(--neo-border-mid)',
            borderRadius: 'var(--mantine-radius-sm)',
            overflow: 'hidden',
          }}
        >
          <Table.ScrollContainer minWidth={860}>
            <Table verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Asked</Table.Th>
                  <Table.Th>Who</Table.Th>
                  <Table.Th>About</Table.Th>
                  <Table.Th>Reason</Table.Th>
                  <Table.Th w={220}>Answer</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={5} p={0}>
                      <EmptyState
                        title={show === 'pending' ? 'Nothing waiting' : 'No requests yet'}
                        text="When an underwriter or a doctor asks to see a client's details, their request and reason appear here."
                      />
                    </Table.Td>
                  </Table.Tr>
                )}
                {rows.map((r) => (
                  <RequestRow key={r.id} row={r} />
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Box>
      )}
    </Stack>
  )
}

function RequestRow({ row }: { row: AccessRequest }) {
  const queryClient = useQueryClient()
  const decide = useMutation({
    mutationFn: (approve: boolean) => decideAccessRequest(row.id, approve),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: ['access-requests'] })
      notifications.show({
        title: updated.status === 'approved' ? 'Approved' : 'Declined',
        message: `${updated.requesterName ?? 'They'} ${
          updated.status === 'approved'
            ? `can see ${updated.clientReference} for the next 24 hours.`
            : `will not see ${updated.clientReference}.`
        }`,
        color: updated.status === 'approved' ? 'teal' : 'gray',
      })
    },
    onError: (e) =>
      notifications.show({ title: 'Could not answer', message: (e as Error).message, color: 'red' }),
  })

  return (
    <Table.Tr style={{ backgroundColor: row.status === 'pending' ? 'var(--neo-warn-soft)' : undefined }}>
      <Table.Td fz="sm" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
        {when(row.createdAt)}
      </Table.Td>
      <Table.Td>
        <Text fz="sm" fw={600}>
          {row.requesterName ?? '—'}
        </Text>
        <Text fz="xs" c="dimmed">
          {row.requesterRole ?? ''}
        </Text>
      </Table.Td>
      <Table.Td>
        <Anchor component={Link} to={`/clients/${row.clientId}`} fz="sm" fw={600}>
          {row.clientName ?? row.clientReference}
        </Anchor>
        <Text fz="xs" ff="monospace" c="dimmed">
          {row.clientReference}
        </Text>
      </Table.Td>
      <Table.Td fz="sm" maw={360}>
        {row.reason}
      </Table.Td>
      <Table.Td>
        {row.status === 'pending' ? (
          <Group gap="xs" wrap="nowrap">
            <Button
              size="compact-sm"
              color="teal"
              leftSection={<IconCheck size={14} />}
              loading={decide.isPending && decide.variables === true}
              disabled={decide.isPending}
              onClick={() => decide.mutate(true)}
            >
              Approve
            </Button>
            <Button
              size="compact-sm"
              variant="light"
              color="gray"
              leftSection={<IconX size={14} />}
              loading={decide.isPending && decide.variables === false}
              disabled={decide.isPending}
              onClick={() => decide.mutate(false)}
            >
              Decline
            </Button>
          </Group>
        ) : (
          <Stack gap={2}>
            <Badge
              size="sm"
              variant="light"
              color={row.status === 'approved' ? 'teal' : 'gray'}
              style={{ minWidth: 'max-content' }}
            >
              {row.status === 'approved' ? 'Approved' : 'Declined'}
            </Badge>
            <Text fz="xs" c="dimmed">
              {row.decidedByName ?? 'An administrator'}
              {row.decidedAt ? `, ${when(row.decidedAt)}` : ''}
            </Text>
            {row.expiresAt && (
              <Text fz="xs" c={new Date(row.expiresAt) > new Date() ? 'teal' : 'dimmed'}>
                {new Date(row.expiresAt) > new Date()
                  ? `Open until ${when(row.expiresAt)}`
                  : 'Expired'}
              </Text>
            )}
          </Stack>
        )}
      </Table.Td>
    </Table.Tr>
  )
}
