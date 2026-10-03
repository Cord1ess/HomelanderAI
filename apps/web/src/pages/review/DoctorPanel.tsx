import {
  Alert,
  Anchor,
  Box,
  Button,
  Group,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconAlertTriangle, IconCircleCheck, IconMail } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { type ApplicationDetail, messageClient, reviewAsDoctor } from '../../api/client'
import { DoctorVerdictBadge } from '../../components/DoctorVerdictBadge'

const URGENT_TEMPLATE =
  'Please see a doctor as soon as possible about the results of your recent medical tests. ' +
  'If you feel unwell, go to the nearest emergency department today.'

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

function ageOn(dateOfBirth: string | null | undefined): number | null {
  if (!dateOfBirth) return null
  const born = new Date(`${dateOfBirth}T00:00:00`)
  const now = new Date()
  let age = now.getFullYear() - born.getFullYear()
  if (now.getMonth() < born.getMonth() || (now.getMonth() === born.getMonth() && now.getDate() < born.getDate())) {
    age -= 1
  }
  return age
}

/**
 * What a doctor does with an application sent to them, in place of the
 * underwriter's decision: check the readers' results and send them back as
 * accurate or inaccurate, and — when something cannot wait for the policy —
 * write to the client directly. Nothing here decides the insurance.
 */
export function DoctorPanel({ data, clientId }: { data: ApplicationDetail; clientId?: string | null }) {
  const queryClient = useQueryClient()
  const [verdict, setVerdict] = useState<'accurate' | 'inaccurate' | null>(null)
  const [note, setNote] = useState('')
  const [urgency, setUrgency] = useState<'urgent' | 'routine'>('urgent')
  const [message, setMessage] = useState(URGENT_TEMPLATE)

  const refresh = (updated: ApplicationDetail) => {
    queryClient.setQueryData(['application', data.id], updated)
    void queryClient.invalidateQueries({ queryKey: ['application', data.id] })
    void queryClient.invalidateQueries({ queryKey: ['applications'] })
    void queryClient.invalidateQueries({ queryKey: ['audit', data.id] })
  }

  const review = useMutation({
    mutationFn: () => reviewAsDoctor(data.id, { verdict: verdict!, note: note.trim() || null }),
    onSuccess: (updated) => {
      refresh(updated)
      setNote('')
      notifications.show({
        title: 'Sent back to the underwriter',
        message: `Tagged “${verdict === 'accurate' ? 'Doctor verified: correct' : 'Doctor verified: wrong'}”.`,
        color: 'teal',
      })
    },
    onError: (e) =>
      notifications.show({ title: 'Could not send it back', message: String((e as Error).message), color: 'red' }),
  })

  const write = useMutation({
    mutationFn: () => messageClient(data.id, { urgency, message: message.trim() }),
    onSuccess: (updated) => {
      refresh(updated)
      notifications.show({
        title: 'Message sent to the client',
        message: 'They will see it on their portal.',
        color: 'teal',
      })
    },
    onError: (e) =>
      notifications.show({ title: 'Could not send the message', message: String((e as Error).message), color: 'red' }),
  })

  const waiting = data.status === 'escalated'
  const reviews = data.doctorReviews ?? []
  const messages = data.clientMessages ?? []
  const age = ageOn(data.applicant.dateOfBirth)

  return (
    <Stack gap="md">
      {/* ── The patient ───────────────────────────────────────── */}
      <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
        <Group justify="space-between" align="baseline" mb="sm">
          <Text fw={600} size="sm">
            Patient
          </Text>
          {clientId && (
            <Anchor component={Link} to={`/clients/${clientId}`} size="xs">
              Open their profile
            </Anchor>
          )}
        </Group>
        <SimpleGrid cols={2} spacing="sm">
          <div>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.4}>
              Name
            </Text>
            <Text size="sm" fw={600}>
              {data.applicant.name || '—'}
            </Text>
          </div>
          <div>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.4}>
              Age · sex
            </Text>
            <Text size="sm" fw={600}>
              {age ?? '—'} · {data.applicant.sex ?? '—'}
            </Text>
          </div>
        </SimpleGrid>
      </Paper>

      {/* ── The verdict ────────────────────────────────────────── */}
      <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
        <Text fw={600} size="sm" mb={4}>
          Your review of the results
        </Text>
        {waiting ? (
          <>
            <Text size="xs" c="dimmed" mb="sm">
              Check the readers' results against the evidence. Your verdict goes back to the
              underwriter as a tag on the results. The insurance decision stays with the underwriter.
            </Text>
            <SegmentedControl
              fullWidth
              size="sm"
              value={verdict ?? ''}
              onChange={(v) => setVerdict(v as 'accurate' | 'inaccurate')}
              data={[
                { value: 'accurate', label: 'Results accurate' },
                { value: 'inaccurate', label: 'Results inaccurate' },
              ]}
            />
            <Textarea
              mt="sm"
              size="xs"
              label="Note for the underwriter"
              description={
                verdict === 'inaccurate'
                  ? 'Say what the readers got wrong — the underwriter decides on your word.'
                  : 'Optional. Anything they should know when they decide.'
              }
              autosize
              minRows={2}
              value={note}
              onChange={(e) => setNote(e.currentTarget.value)}
            />
            <Button
              mt="sm"
              fullWidth
              onClick={() => review.mutate()}
              loading={review.isPending}
              disabled={!verdict || (verdict === 'inaccurate' && note.trim().length < 3)}
            >
              Send back to the underwriter
            </Button>
          </>
        ) : (
          <Text size="xs" c="dimmed" mb="sm">
            {reviews.length
              ? 'You have sent this back to the underwriter. It returns here if they send it again.'
              : 'Not waiting for you.'}
          </Text>
        )}

        {reviews.length > 0 && (
          <Stack gap={6} mt="md">
            {reviews.map((r) => (
              <Box key={r.createdAt}>
                <Group gap={6}>
                  <DoctorVerdictBadge verdict={r.verdict} size="xs" />
                  <Text size="xs" c="dimmed">
                    {r.doctorName ?? 'A doctor'} · {when(r.createdAt)}
                  </Text>
                </Group>
                {r.note && (
                  <Text size="xs" mt={2}>
                    {r.note}
                  </Text>
                )}
              </Box>
            ))}
          </Stack>
        )}
      </Paper>

      {/* ── Writing to the client ─────────────────────────────── */}
      <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
        <Group gap={6} mb={4}>
          <IconMail size={16} />
          <Text fw={600} size="sm">
            Write to the client directly
          </Text>
        </Group>
        <Text size="xs" c="dimmed" mb="sm">
          For what cannot wait for the policy. The client reads it on their portal, and by email
          when mail is set up. Write as you would to a patient: no scores, no model names.
        </Text>
        <SegmentedControl
          fullWidth
          size="xs"
          value={urgency}
          onChange={(v) => {
            setUrgency(v as 'urgent' | 'routine')
            if (v === 'urgent' && !message.trim()) setMessage(URGENT_TEMPLATE)
          }}
          data={[
            { value: 'urgent', label: 'Urgent' },
            { value: 'routine', label: 'Advice' },
          ]}
        />
        <Textarea
          mt="sm"
          size="xs"
          autosize
          minRows={3}
          value={message}
          onChange={(e) => setMessage(e.currentTarget.value)}
        />
        <Button
          mt="sm"
          fullWidth
          variant="light"
          color={urgency === 'urgent' ? 'red' : undefined}
          leftSection={urgency === 'urgent' ? <IconAlertTriangle size={14} /> : <IconMail size={14} />}
          onClick={() => write.mutate()}
          loading={write.isPending}
          disabled={message.trim().length < 3}
        >
          Send to the client
        </Button>

        {messages.length > 0 && (
          <Stack gap={6} mt="md">
            {messages.map((m) => (
              <Alert
                key={m.createdAt}
                variant="light"
                color={m.urgency === 'urgent' ? 'red' : 'gray'}
                icon={m.urgency === 'urgent' ? <IconAlertTriangle size={14} /> : <IconCircleCheck size={14} />}
                p="xs"
              >
                <Text size="xs">{m.message}</Text>
                <Text size="xs" c="dimmed" mt={2}>
                  {m.senderName ?? 'A doctor'} · {when(m.createdAt)}
                  {m.emailed ? ' · emailed' : ' · on their portal'}
                </Text>
              </Alert>
            ))}
          </Stack>
        )}
      </Paper>
    </Stack>
  )
}
