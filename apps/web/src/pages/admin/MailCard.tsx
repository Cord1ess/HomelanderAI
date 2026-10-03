import { Badge, Button, Code, Group, Paper, Stack, Table, Text, TextInput } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconMail } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { getMailStatus, sendTestMail } from '../../api/client'

const STATUS: Record<string, { label: string; color: string }> = {
  sent: { label: 'Sent', color: 'teal' },
  not_configured: { label: 'Not sent: not set up', color: 'orange' },
  failed: { label: 'Failed', color: 'red' },
}

/**
 * Outgoing email: whether it is set up, a test message, and what was sent.
 *
 * The server is configured in the API's .env (SMTP_HOST and friends), not
 * here: those are credentials, and a credential typed into a web page ends up
 * in a database. This card says what is in place and proves it works.
 */
export function MailCard() {
  const queryClient = useQueryClient()
  const { data } = useQuery({ queryKey: ['mail-status'], queryFn: getMailStatus })
  const [to, setTo] = useState('')
  const test = useMutation({
    mutationFn: () => sendTestMail(to.trim()),
    onSuccess: (status) => {
      queryClient.setQueryData(['mail-status'], status)
      const latest = status.recent?.[0]
      notifications.show({
        title: latest?.status === 'sent' ? 'Test message sent' : 'Not sent',
        message:
          latest?.status === 'sent'
            ? `Check ${to} for it.`
            : status.configured
              ? 'The mail server refused it. Check the settings in the API .env and its log.'
              : 'Email is not set up yet. Fill in SMTP_HOST and the rest in the API .env, then restart the API.',
        color: latest?.status === 'sent' ? 'teal' : 'orange',
      })
    },
    onError: (e) => notifications.show({ title: 'Could not send', message: (e as Error).message, color: 'red' }),
  })

  return (
    <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
      <Group justify="space-between" mb={4}>
        <Group gap={6}>
          <IconMail size={16} />
          <Text fw={600} size="sm">
            Email to clients
          </Text>
        </Group>
        {data && (
          <Badge color={data.configured ? 'teal' : 'orange'} variant="light">
            {data.configured ? 'Set up' : 'Not set up yet'}
          </Badge>
        )}
      </Group>
      <Text size="xs" c="dimmed" mb="sm">
        Clients are emailed their portal sign-in, a note when there is an update, and any message a doctor writes
        them. Until email is set up, staff are shown the sign-in to hand over instead.
      </Text>

      {data && (
        <Stack gap={4} mb="sm">
          <Text size="xs">
            Server: <Code>{data.host ? `${data.host}:${data.port}` : 'none'}</Code> · From: <Code>{data.sender}</Code>
          </Text>
          <Text size="xs">
            Links in emails go to: <Code>{data.portalUrl}</Code>
          </Text>
          {!data.configured && (
            <Text size="xs" c="dimmed">
              To set it up, fill in <Code>SMTP_HOST</Code>, <Code>SMTP_PORT</Code>, <Code>SMTP_USER</Code>,{' '}
              <Code>SMTP_PASSWORD</Code> and <Code>SMTP_FROM</Code> in the API's <Code>.env</Code> (Gmail works with an app
              password), set <Code>PORTAL_URL</Code> to the address clients use, and restart the API.
            </Text>
          )}
        </Stack>
      )}

      <Group align="flex-end" gap="sm">
        <TextInput
          style={{ flex: 1 }}
          size="xs"
          label="Send a test message to"
          placeholder="you@company.com"
          value={to}
          onChange={(e) => setTo(e.currentTarget.value)}
        />
        <Button size="xs" onClick={() => test.mutate()} loading={test.isPending} disabled={!to.includes('@')}>
          Send test
        </Button>
      </Group>

      {(data?.recent ?? []).length > 0 && (
        <Table mt="md" verticalSpacing={4} fz="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>When</Table.Th>
              <Table.Th>To</Table.Th>
              <Table.Th>Subject</Table.Th>
              <Table.Th>Result</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(data?.recent ?? []).slice(0, 8).map((e, i) => (
              <Table.Tr key={`${e.createdAt}-${i}`}>
                <Table.Td>
                  {new Date(e.createdAt).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                </Table.Td>
                <Table.Td>{e.recipient}</Table.Td>
                <Table.Td>{e.subject}</Table.Td>
                <Table.Td>
                  <Badge size="xs" variant="light" color={STATUS[e.status]?.color ?? 'gray'} style={{ minWidth: 'max-content' }}>
                    {STATUS[e.status]?.label ?? e.status}
                  </Badge>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Paper>
  )
}
