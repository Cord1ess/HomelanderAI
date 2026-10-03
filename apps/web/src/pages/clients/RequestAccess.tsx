import { Alert, Button, Modal, Stack, Text, Textarea } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconClock, IconLock, IconSend } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { getAccessRequests, requestClientAccess } from '../../api/client'

/**
 * Asking the company owner to see one client's personal details, with a
 * reason. Used from the clients list (in a dialog) and from a client's
 * profile opened without permission (on the page itself).
 */
export function RequestAccessForm({
  clientId,
  reference,
  name,
  onSent,
}: {
  clientId: string
  reference: string
  name?: string | null
  onSent?: () => void
}) {
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('')

  // Your own requests: the newest one about this client says where it stands.
  const mine = useQuery({ queryKey: ['access-requests'], queryFn: getAccessRequests })
  const latest = (mine.data ?? []).find((r) => r.clientId === clientId)

  const send = useMutation({
    mutationFn: () => requestClientAccess(clientId, reason.trim()),
    onSuccess: () => {
      setReason('')
      void queryClient.invalidateQueries({ queryKey: ['access-requests'] })
      void queryClient.invalidateQueries({ queryKey: ['clients'] })
      notifications.show({
        title: 'Request sent',
        message: 'The administrator has been told. You will get a notification when they answer.',
        color: 'teal',
      })
      onSent?.()
    },
    onError: (e) =>
      notifications.show({ title: 'Could not send', message: (e as Error).message, color: 'red' }),
  })

  if (latest?.status === 'pending') {
    return (
      <Alert color="orange" variant="light" icon={<IconClock size={18} />} title="Waiting for the administrator">
        <Text size="sm">
          You asked to see {name ?? reference}'s details on{' '}
          {new Date(latest.createdAt).toLocaleString(undefined, {
            day: 'numeric',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit',
          })}
          . You will get a notification when they answer.
        </Text>
        <Text size="xs" c="dimmed" mt={6}>
          Your reason: {latest.reason}
        </Text>
      </Alert>
    )
  }

  return (
    <Stack gap="sm">
      <Text size="sm">
        A client's phone, email, portal sign-in, date of birth and test results are only shown to
        the company owner. Tell the administrator why you need {name ?? reference}'s details. If
        they approve, you can see them for 24 hours.
      </Text>
      {latest?.status === 'declined' && (
        <Alert color="gray" variant="light" p="xs">
          <Text size="xs">Your last request was declined. You can ask again with a clearer reason.</Text>
        </Alert>
      )}
      <Textarea
        label="Why do you need this client's details?"
        placeholder="For example: I need their phone number to book the follow-up medical."
        autosize
        minRows={3}
        maxLength={1000}
        value={reason}
        onChange={(e) => setReason(e.currentTarget.value)}
      />
      <Button
        leftSection={<IconSend size={14} />}
        onClick={() => send.mutate()}
        loading={send.isPending}
        disabled={reason.trim().length < 5}
      >
        Send request to the administrator
      </Button>
    </Stack>
  )
}

export function RequestAccessModal({
  client,
  onClose,
}: {
  client: { id: string; reference: string; name?: string | null } | null
  onClose: () => void
}) {
  return (
    <Modal
      opened={Boolean(client)}
      onClose={onClose}
      title={
        <Text fw={700} size="sm">
          <IconLock size={14} style={{ verticalAlign: '-2px', marginRight: 6 }} />
          Request to view {client?.name ?? client?.reference ?? 'this client'}'s details
        </Text>
      }
      centered
    >
      {client && (
        <RequestAccessForm
          clientId={client.id}
          reference={client.reference}
          name={client.name}
          onSent={onClose}
        />
      )}
    </Modal>
  )
}
