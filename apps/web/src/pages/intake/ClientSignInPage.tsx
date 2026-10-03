import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  CopyButton,
  Group,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconCircleCheck, IconCopy, IconEye, IconEyeOff, IconKey, IconMail } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'

import { getClientSignIn, reissueClientSignIn, type ClientSignIn, type PortalCredentials } from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { ErrorState, LoadingState } from '../../components/states'

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

const KIND: Record<string, string> = {
  portal_sign_in: 'Portal sign-in',
  decision_notice: 'Decision notice',
  doctor_message: "Doctor's message",
  policy_update: 'Policy update',
  test: 'Test message',
}

const STATUS: Record<string, { label: string; color: string }> = {
  sent: { label: 'Sent', color: 'teal' },
  not_configured: { label: 'Not sent: email not set up', color: 'orange' },
  failed: { label: 'Failed', color: 'red' },
}

/**
 * A client's portal sign-in, after intake.
 *
 * Opened straight after an application is submitted, with the sign-in that was
 * just made, and again from the Applications list whenever the email did not
 * arrive. The password is never stored, so "again" always means a new one:
 * emailed when possible, or shown once here to hand over.
 */
export function ClientSignInPage() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const queryClient = useQueryClient()
  const handed = (location.state as { portal?: PortalCredentials | null; justSubmitted?: boolean } | null) ?? null

  const [password, setPassword] = useState<string | null>(handed?.portal?.password ?? null)
  const [shown, setShown] = useState(false)
  const [email, setEmail] = useState<string | null>(null)

  const page = useQuery({
    queryKey: ['client-sign-in', id],
    queryFn: () => getClientSignIn(id!),
    enabled: Boolean(id),
  })

  const reissue = useMutation({
    mutationFn: (sendEmail: boolean) =>
      reissueClientSignIn(id!, {
        sendEmail,
        email: email !== null && email !== page.data?.email ? email : undefined,
      }),
    onSuccess: (result: ClientSignIn) => {
      queryClient.setQueryData(['client-sign-in', id], result)
      setEmail(null)
      setPassword(result.password ?? null)
      setShown(false)
      notifications.show({
        title: result.emailed ? 'New sign-in emailed' : 'New password made',
        message: result.emailed
          ? `Sent to ${result.email}. The old password no longer works.`
          : 'Hand it to the client now. The old password no longer works.',
        color: 'teal',
      })
    },
    onError: (e) => notifications.show({ title: 'Could not do that', message: (e as Error).message, color: 'red' }),
  })

  if (page.isPending) return <LoadingState label="Loading the client's sign-in" />
  if (page.error || !page.data) {
    return <ErrorState title="Could not load the sign-in" error={page.error} retry={() => void page.refetch()} />
  }
  const d = page.data
  const emailValue = email ?? (d.detailsVisible ? (d.email ?? '') : '')
  // Whoever just took the application was given the whole id with it, to hand
  // over; masking it here would leave them nothing to give the client.
  const portalId = handed?.portal?.portalId ?? d.portalId
  const idVisible = d.detailsVisible || Boolean(handed?.portal?.portalId)
  const emailedAtIntake = handed?.portal?.emailed

  return (
    <Stack gap="md" maw={880}>
      <PageHeader
        screen="intake"
        title={
          <span>
            Client sign-in <span className="hl-mono">{d.reference}</span>
          </span>
        }
        description={`${d.clientName ?? 'The client'} follows their application on the client portal with this sign-in.`}
        actions={
          <Group gap="xs">
            <Button component={Link} to="/queue" size="xs" variant="default">
              All applications
            </Button>
            <Button component={Link} to={`/applications/${d.applicationId}`} size="xs">
              Open the application
            </Button>
          </Group>
        }
      />

      {handed?.justSubmitted && (
        <Alert color="teal" variant="light" icon={<IconCircleCheck size={18} />} title="Application submitted">
          <Text size="sm">
            {d.reference} is in. The models are reading the evidence now; you can watch the progress on the
            Applications page.
          </Text>
        </Alert>
      )}

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        <Paper p="md" bd="1px solid var(--neo-border-mid)">
          <Group gap={6} mb="sm">
            <IconKey size={16} />
            <Text fw={700} size="sm">
              Portal sign-in
            </Text>
          </Group>
          <Row label="Portal ID" value={portalId ?? '—'} copy={idVisible ? (portalId ?? undefined) : undefined} mono />
          <Box mt="sm">
            <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.4}>
              One-time password
            </Text>
            {password ? (
              <Group gap="xs" mt={4} wrap="nowrap">
                <Text ff="monospace" fw={700} size="lg" style={{ letterSpacing: shown ? 0.5 : 3 }}>
                  {shown ? password : '•'.repeat(Math.max(8, password.length))}
                </Text>
                <Tooltip label={shown ? 'Hide' : 'Show'} withArrow>
                  <ActionIcon variant="light" onClick={() => setShown((s) => !s)} aria-label={shown ? 'Hide the password' : 'Show the password'}>
                    {shown ? <IconEyeOff size={16} /> : <IconEye size={16} />}
                  </ActionIcon>
                </Tooltip>
                <CopyButton value={password}>
                  {({ copied, copy }) => (
                    <Tooltip label={copied ? 'Copied' : 'Copy'} withArrow>
                      <ActionIcon variant="light" color={copied ? 'teal' : undefined} onClick={copy} aria-label="Copy the password">
                        <IconCopy size={16} />
                      </ActionIcon>
                    </Tooltip>
                  )}
                </CopyButton>
              </Group>
            ) : (
              <Text size="sm" mt={4} c="dimmed">
                {emailedAtIntake
                  ? `Emailed to ${handed?.portal?.email}. It is not stored, so it cannot be shown here.`
                  : 'Not stored, so it cannot be shown again. Make a new one below if the client needs it.'}
              </Text>
            )}
            {password && (
              <Text size="xs" c="orange" mt={6}>
                Shown only now: it is not stored. Give it to the client before you leave this page.
              </Text>
            )}
          </Box>
          <Text size="xs" c="dimmed" mt="md">
            The client signs in on the client portal (Check status on the home page), with their portal ID and this password.
          </Text>
        </Paper>

        <Paper p="md" bd="1px solid var(--neo-border-mid)">
          <Group gap={6} mb="sm">
            <IconMail size={16} />
            <Text fw={700} size="sm">
              Send it again
            </Text>
          </Group>
          {!d.mailConfigured && (
            <Alert color="orange" variant="light" p="xs" mb="sm">
              <Text size="xs">
                Email is not set up yet, so nothing can be sent. Make a new password and hand it over in person;
                the administrator sets up email in Company settings.
              </Text>
            </Alert>
          )}
          <TextInput
            label="Client's email"
            description={
              d.detailsVisible
                ? 'Correct it here if it was wrong.'
                : `On file: ${d.email ?? 'none'}. Type a corrected address to replace it.`
            }
            placeholder="client@example.com"
            value={emailValue}
            onChange={(e) => setEmail(e.currentTarget.value)}
          />
          <Group mt="sm" gap="xs">
            <Button
              size="xs"
              leftSection={<IconMail size={14} />}
              disabled={!d.mailConfigured || (!d.email && !email)}
              loading={reissue.isPending && reissue.variables === true}
              onClick={() => reissue.mutate(true)}
            >
              Email a new sign-in
            </Button>
            <Button
              size="xs"
              variant="default"
              leftSection={<IconKey size={14} />}
              loading={reissue.isPending && reissue.variables === false}
              onClick={() => reissue.mutate(false)}
            >
              Make a new password to hand over
            </Button>
          </Group>
          <Text size="xs" c="dimmed" mt="sm">
            Either way the old password stops working.
          </Text>
        </Paper>
      </SimpleGrid>

      <Paper p="md" bd="1px solid var(--neo-border-mid)">
        <Text fw={700} size="sm" mb="xs">
          Emails to this client
        </Text>
        {d.emails && d.emails.length > 0 ? (
          <Table verticalSpacing={6}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>When</Table.Th>
                <Table.Th>What</Table.Th>
                <Table.Th>To</Table.Th>
                <Table.Th>Result</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {d.emails.map((e, i) => (
                <Table.Tr key={`${e.createdAt}-${i}`}>
                  <Table.Td fz="sm">{when(e.createdAt)}</Table.Td>
                  <Table.Td fz="sm">{KIND[e.kind] ?? e.kind}</Table.Td>
                  <Table.Td fz="sm">{e.recipient}</Table.Td>
                  <Table.Td>
                    <Badge size="sm" variant="light" color={STATUS[e.status]?.color ?? 'gray'} style={{ minWidth: 'max-content' }}>
                      {STATUS[e.status]?.label ?? e.status}
                    </Badge>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : (
          <Text size="sm" c="dimmed">
            Nothing has been emailed to this client yet.
          </Text>
        )}
      </Paper>

      <Anchor component={Link} to="/queue" size="sm">
        Back to all applications
      </Anchor>
    </Stack>
  )
}

function Row({ label, value, copy, mono }: { label: string; value: string; copy?: string; mono?: boolean }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.4}>
        {label}
      </Text>
      <Group gap="xs" mt={4} wrap="nowrap">
        <Text ff={mono ? 'monospace' : undefined} fw={700} size="lg">
          {value}
        </Text>
        {copy && (
          <CopyButton value={copy}>
            {({ copied, copy: doCopy }) => (
              <Tooltip label={copied ? 'Copied' : 'Copy'} withArrow>
                <ActionIcon variant="light" color={copied ? 'teal' : undefined} onClick={doCopy} aria-label={`Copy the ${label}`}>
                  <IconCopy size={16} />
                </ActionIcon>
              </Tooltip>
            )}
          </CopyButton>
        )}
      </Group>
    </div>
  )
}
