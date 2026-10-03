import { Alert, Anchor, Badge, Box, Button, Checkbox, Group, Modal, Stack, Table, Text, Textarea } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconAlertTriangle } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { decideDeletion, getDeletionRequests, type Deletion } from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { Stat } from '../../components/Stat'
import { EmptyState, ErrorState, LoadingState } from '../../components/states'

const day = (iso: string) =>
  new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })

const STATUS: Record<string, { label: string; color: string }> = {
  pending: { label: 'Waiting for you', color: 'orange' },
  approved: { label: 'Approved, deleting on the date', color: 'blue' },
  declined: { label: 'Declined', color: 'gray' },
  withdrawn: { label: 'Withdrawn by the client', color: 'gray' },
  completed: { label: 'Deleted', color: 'teal' },
}

/**
 * Clients asking for their data to be deleted. Approve and it is erased on the
 * thirtieth day after they asked (or now); decline and say why. A policy in
 * force or an open claim stops it until it is dealt with.
 */
export function DataRequestsPage() {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['deletion-requests'],
    queryFn: getDeletionRequests,
    refetchInterval: 60_000,
  })
  const rows = data ?? []
  return (
    <Stack gap="md">
      <PageHeader screen="dataRequests">
        <Group gap="xs" grow>
          <Stat label="Waiting for you" value={rows.filter((r) => r.status === 'pending').length} color="orange" />
          <Stat label="Approved" value={rows.filter((r) => r.status === 'approved').length} color="blue" hint="Erased on their date" />
          <Stat label="Deleted" value={rows.filter((r) => r.status === 'completed').length} color="teal" />
        </Group>
      </PageHeader>
      {isPending && <LoadingState label="Loading requests" />}
      {error && !data && <ErrorState title="Could not load the requests" error={error} retry={() => void refetch()} />}
      {data && (
        <Box style={{ border: '1px solid var(--neo-border-mid)', borderRadius: 'var(--mantine-radius-sm)', overflow: 'hidden' }}>
          <Table.ScrollContainer minWidth={820}>
            <Table verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Client</Table.Th>
                  <Table.Th>Asked</Table.Th>
                  <Table.Th>Reason</Table.Th>
                  <Table.Th>Delete by</Table.Th>
                  <Table.Th w={260}>Answer</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={5} p={0}>
                      <EmptyState title="No requests" text="When a client asks from their portal for their data to be deleted, it appears here." />
                    </Table.Td>
                  </Table.Tr>
                )}
                {rows.map((r) => (
                  <Row key={r.id} row={r} />
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Box>
      )}
    </Stack>
  )
}

function Row({ row }: { row: Deletion }) {
  const queryClient = useQueryClient()
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')
  const [now, setNow] = useState(false)
  const decide = useMutation({
    mutationFn: (approve: boolean) => decideDeletion(row.id, { approve, reason: approve ? null : reason.trim(), now: approve && now }),
    onSuccess: (r) => {
      void queryClient.invalidateQueries({ queryKey: ['deletion-requests'] })
      setDeclining(false)
      notifications.show({
        title: STATUS[r.status]?.label ?? 'Done',
        message: r.status === 'completed' ? 'The client\'s personal data has been erased.' : `Client ${r.clientReference}`,
        color: 'teal',
      })
    },
    onError: (e) => notifications.show({ title: 'Could not do that', message: (e as Error).message, color: 'red' }),
  })
  const blockers = row.blockers ?? []
  return (
    <Table.Tr style={{ backgroundColor: row.status === 'pending' ? 'var(--neo-warn-soft)' : undefined }}>
      <Table.Td>
        <Anchor component={Link} to={`/clients/${row.clientId}`} fz="sm" fw={600}>
          {row.clientName ?? row.clientReference}
        </Anchor>
        <Text fz="xs" c="dimmed" ff="monospace">
          {row.clientReference}
        </Text>
      </Table.Td>
      <Table.Td fz="sm">{day(row.requestedAt)}</Table.Td>
      <Table.Td fz="sm" maw={280}>
        {row.reason ?? <Text span c="dimmed" fz="sm">No reason given</Text>}
      </Table.Td>
      <Table.Td fz="sm">{day(row.deleteOn)}</Table.Td>
      <Table.Td>
        {row.status === 'pending' ? (
          <Stack gap={6}>
            {blockers.length > 0 && (
              <Alert color="orange" variant="light" p={6} icon={<IconAlertTriangle size={14} />}>
                {blockers.map((b) => (
                  <Text key={b} size="xs">
                    {b}
                  </Text>
                ))}
              </Alert>
            )}
            <Checkbox size="xs" label="Delete now, not on the date" checked={now} onChange={(e) => setNow(e.currentTarget.checked)} />
            <Group gap="xs">
              <Button size="compact-sm" color="teal" disabled={blockers.length > 0} loading={decide.isPending && decide.variables} onClick={() => decide.mutate(true)}>
                Approve
              </Button>
              <Button size="compact-sm" variant="light" color="gray" onClick={() => setDeclining(true)}>
                Decline
              </Button>
            </Group>
          </Stack>
        ) : (
          <Stack gap={2}>
            <Badge size="sm" variant="light" color={STATUS[row.status]?.color ?? 'gray'} style={{ minWidth: 'max-content' }}>
              {STATUS[row.status]?.label ?? row.status}
            </Badge>
            {row.declineReason && <Text size="xs">{row.declineReason}</Text>}
            {row.completedAt && <Text size="xs" c="dimmed">Erased {day(row.completedAt)}</Text>}
            {row.decidedByName && <Text size="xs" c="dimmed">{row.decidedByName}</Text>}
          </Stack>
        )}
        <Modal opened={declining} onClose={() => setDeclining(false)} title="Decline the request" centered>
          <Stack gap="sm">
            <Textarea label="Why" description="The client reads this." autosize minRows={3} value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
            <Button color="gray" disabled={reason.trim().length < 3} loading={decide.isPending} onClick={() => decide.mutate(false)}>
              Decline
            </Button>
          </Stack>
        </Modal>
      </Table.Td>
    </Table.Tr>
  )
}
