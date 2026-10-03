import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Textarea,
  Tooltip,
  UnstyledButton,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconCircleCheck, IconCircleX, IconHandGrab, IconPlus } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  assignApplication,
  escalateApplication,
  quoteApplication,
  recordDecision,
  type ApplicationDetail,
} from '../../api/client'
import { useAuth } from '../../context/AuthContext'

const taka = (v: string | number) => `৳${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
const day = (iso: string) =>
  new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })

/** Mirrors app/decline.py: the code, and what the underwriter sees. */
const DECLINE_REASONS = [
  { value: 'medical_risk', label: 'The medical evidence shows a risk too high to insure' },
  { value: 'under_treatment', label: 'A condition under treatment: postpone until it is resolved' },
  { value: 'non_disclosure', label: 'What was declared does not match the evidence' },
  { value: 'incomplete_evidence', label: 'The documents asked for were not provided' },
  { value: 'outside_limits', label: "Outside the product's limits (age or amount)" },
  { value: 'other', label: 'Another reason (explain in the note)' },
]
const RATINGS = [0, 25, 50, 75, 100, 150]

type Choice = 'standard' | 'adjusted' | 'decline' | 'doctor'

/**
 * The decision, with its terms. Approve at standard rates, approve with
 * adjusted terms (a rating on the premium and, for hospital cover,
 * exclusions), decline with a reason the client reads, or send to a doctor.
 * The premium is the pricing engine's, shown live; it is never typed.
 */
export function DecisionPanel({
  data,
  isElevated,
  reviewedByDoctor,
}: {
  data: ApplicationDetail
  isElevated: boolean
  reviewedByDoctor: boolean
}) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const isAdmin = user?.role === 'admin'
  const isUnderwriter = user?.role === 'underwriter'
  const escalated = data.status === 'escalated'
  const decided = Boolean(data.decision)
  const health = data.product === 'health'
  const [choice, setChoice] = useState<Choice | null>(null)
  const [rating, setRating] = useState<number>(data.plan?.ratingPct ?? 50)
  const [exclusions, setExclusions] = useState<string[]>(health ? (data.suggestedExclusions ?? []) : [])
  const [custom, setCustom] = useState('')
  const [declineReason, setDeclineReason] = useState<string | null>(null)
  const [declineNote, setDeclineNote] = useState('')
  const [reapply, setReapply] = useState<string | null>(null)
  const [doctorNote, setDoctorNote] = useState('')

  const priceRating = choice === 'adjusted' ? rating : 0
  const priced = useQuery({
    queryKey: ['quote', data.id, priceRating],
    queryFn: () => quoteApplication(data.id, priceRating),
    enabled: !decided && (choice === 'standard' || choice === 'adjusted'),
  })

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['application', data.id] })
    void queryClient.invalidateQueries({ queryKey: ['applications'] })
    void queryClient.invalidateQueries({ queryKey: ['audit', data.id] })
  }
  const submit = useMutation({
    mutationFn: async () => {
      if (choice === 'doctor') return void (await escalateApplication(data.id, { note: doctorNote.trim() || null }))
      if (choice === 'decline') {
        return void (await recordDecision(data.id, {
          decision: 'declined',
          declineReason,
          declineNote: declineNote.trim() || null,
          reapplyAfterMonths: reapply ? Number(reapply) : null,
        }))
      }
      await recordDecision(data.id, {
        decision: choice === 'standard' ? 'confirmed_fast_track' : 'approved_with_adjustment',
        ratingPct: choice === 'adjusted' ? rating : 0,
        exclusions: choice === 'adjusted' && health ? exclusions : [],
      })
    },
    onSuccess: () => {
      refresh()
      notifications.show({
        title: choice === 'doctor' ? 'Sent to a doctor' : choice === 'decline' ? 'Declined' : 'Approved',
        message:
          choice === 'doctor'
            ? 'The doctors have been told.'
            : choice === 'decline'
              ? 'The client sees the reason on their portal.'
              : 'The policy is issued. The client sees it on their portal.',
        color: choice === 'decline' ? 'gray' : 'teal',
      })
    },
    onError: (e) => notifications.show({ title: 'Could not record it', message: (e as Error).message, color: 'red' }),
  })
  const take = useMutation({
    mutationFn: (release: boolean) => assignApplication(data.id, release),
    onSuccess: (updated) => {
      queryClient.setQueryData(['application', data.id], updated)
      void queryClient.invalidateQueries({ queryKey: ['applications'] })
    },
    onError: (e) => notifications.show({ title: 'Could not take it', message: (e as Error).message, color: 'red' }),
  })

  const mine = data.assignedToId === user?.id
  const blocked = (escalated && !isAdmin) || (isUnderwriter && isElevated && !reviewedByDoctor)
  const blockedWhy = escalated
    ? 'A doctor has it: decide once they send it back.'
    : 'Elevated risk: a doctor checks the results first.'
  const scoring = data.status === 'submitted' || data.status === 'processing'

  const choices: { value: Choice; title: string; text: string; hidden?: boolean; disabled?: boolean }[] = [
    { value: 'standard', title: 'Approve at standard rates', text: 'The premium for this client, nothing added.', disabled: blocked },
    {
      value: 'adjusted',
      title: 'Approve with adjusted terms',
      text: health ? 'A rating on the premium, exclusions, or both.' : 'A rating on the premium.',
      disabled: blocked,
    },
    { value: 'decline', title: 'Decline', text: 'With a reason the client reads.', disabled: blocked },
    { value: 'doctor', title: 'Send to a doctor', text: 'A doctor checks the results first.', hidden: escalated },
  ]

  const ready =
    choice === 'doctor' ||
    (choice === 'decline' && declineReason && (declineReason !== 'other' || declineNote.trim().length >= 5)) ||
    ((choice === 'standard' || choice === 'adjusted') &&
      priced.data?.eligible &&
      (choice === 'standard' || rating > 0 || exclusions.length > 0))

  return (
    <Stack gap="sm">
      {user?.role !== 'medical_professional' && !decided && (
        <Group justify="flex-end" gap={6}>
            {data.assignedToName && (
              <Badge size="sm" variant="light" color={mine ? 'teal' : 'gray'} style={{ minWidth: 'max-content' }}>
                {mine ? 'You have this case' : `${data.assignedToName} has this case`}
              </Badge>
            )}
            {mine ? (
              <Button size="compact-xs" variant="subtle" color="gray" onClick={() => take.mutate(true)} loading={take.isPending}>
                Hand back
              </Button>
            ) : (
              (!data.assignedToId || isAdmin) && (
                <Button size="compact-xs" variant="light" leftSection={<IconHandGrab size={12} />} onClick={() => take.mutate(false)} loading={take.isPending}>
                  Take this case
                </Button>
              )
            )}
        </Group>
      )}

      {decided ? (
        <Recorded data={data} />
      ) : scoring ? (
        <Text size="sm" c="dimmed">
          A decision can be made once the models have finished reading the evidence.
        </Text>
      ) : (
        <Stack gap="sm">
          <SimpleGrid cols={1} spacing={6}>
            {choices
              .filter((c) => !c.hidden)
              .map((c) => {
                const card = (
                  <UnstyledButton
                    key={c.value}
                    onClick={() => !c.disabled && setChoice(c.value)}
                    p="xs"
                    style={{
                      border: `1.5px solid ${choice === c.value ? (c.value === 'decline' ? 'var(--neo-danger)' : 'var(--neo-forest)') : 'var(--neo-border-mid)'}`,
                      background: choice === c.value ? 'var(--neo-accent-soft)' : 'var(--neo-card)',
                      borderRadius: 6,
                      opacity: c.disabled ? 0.5 : 1,
                      cursor: c.disabled ? 'not-allowed' : 'pointer',
                    }}
                    aria-pressed={choice === c.value}
                  >
                    <Text size="sm" fw={700}>
                      {c.title}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {c.text}
                    </Text>
                  </UnstyledButton>
                )
                return c.disabled ? (
                  <Tooltip key={c.value} label={blockedWhy} withArrow>
                    <div>{card}</div>
                  </Tooltip>
                ) : (
                  card
                )
              })}
          </SimpleGrid>

          {choice === 'adjusted' && (
            <Stack gap="xs">
              <Select
                size="xs"
                label="Rating: extra on the premium"
                description={`The models suggest ${data.plan?.ratingPct != null ? `+${data.plan.ratingPct}%` : 'none'} for this tier.`}
                data={RATINGS.map((r) => ({ value: String(r), label: r === 0 ? 'None (standard)' : `+${r}%` }))}
                value={String(rating)}
                onChange={(v) => v && setRating(Number(v))}
                allowDeselect={false}
              />
              {health && (
                <Stack gap={4}>
                  <Text size="xs" fw={600}>
                    Exclusions: what the policy will not pay for
                  </Text>
                  {[...new Set([...(data.suggestedExclusions ?? []), ...exclusions])].map((e) => (
                    <Checkbox
                      key={e}
                      size="xs"
                      label={e}
                      checked={exclusions.includes(e)}
                      onChange={(ev) =>
                        setExclusions((p) => (ev.currentTarget.checked ? [...p, e] : p.filter((x) => x !== e)))
                      }
                    />
                  ))}
                  <Group gap={6} align="flex-end">
                    <TextInput size="xs" placeholder="Another condition, in plain words" value={custom} onChange={(e) => setCustom(e.currentTarget.value)} style={{ flex: 1 }} />
                    <Button
                      size="xs"
                      variant="default"
                      leftSection={<IconPlus size={12} />}
                      disabled={custom.trim().length < 3}
                      onClick={() => {
                        setExclusions((p) => [...p, custom.trim()])
                        setCustom('')
                      }}
                    >
                      Add
                    </Button>
                  </Group>
                </Stack>
              )}
            </Stack>
          )}

          {(choice === 'standard' || choice === 'adjusted') && priced.data && (
            priced.data.eligible ? (
              <Alert color="teal" variant="light" p="xs">
                <Text size="sm" fw={700}>
                  {taka(priced.data.monthlyBdt)} a month, or {taka(priced.data.annualBdt)} a year
                </Text>
                <Text size="xs" c="dimmed">
                  {health ? 'Hospital cover for one year' : `Term life for ${priced.data.termYears} years`} on{' '}
                  {taka(priced.data.sumAssuredBdt)}, age {priced.data.age}
                  {priced.data.smoker ? ', declared smoker' : ''}. Paid {data.coverage.paymentMode === 'yearly' ? 'yearly' : 'monthly'} through the bank.
                </Text>
              </Alert>
            ) : (
              <Alert color="red" variant="light" p="xs">
                <Text size="sm">{priced.data.reason}</Text>
                <Text size="xs" c="dimmed">
                  Decline it as outside the product's limits.
                </Text>
              </Alert>
            )
          )}

          {choice === 'decline' && (
            <Stack gap="xs">
              <Select size="xs" label="Why" data={DECLINE_REASONS} value={declineReason} onChange={setDeclineReason} placeholder="Choose a reason" />
              <Textarea
                size="xs"
                label="A note for the client"
                description="Optional (required for 'another reason'). They read it on their portal: plain words, no scores or findings."
                autosize
                minRows={2}
                value={declineNote}
                onChange={(e) => setDeclineNote(e.currentTarget.value)}
              />
              <Select
                size="xs"
                label="They may apply again"
                data={[
                  { value: '3', label: 'After 3 months' },
                  { value: '6', label: 'After 6 months' },
                  { value: '12', label: 'After a year' },
                  { value: '24', label: 'After two years' },
                ]}
                value={reapply}
                onChange={setReapply}
                clearable
                placeholder="No date"
              />
            </Stack>
          )}

          {choice === 'doctor' && (
            <Textarea
              size="xs"
              label="A note for the doctor"
              description="Optional. What you want them to look at."
              autosize
              minRows={2}
              value={doctorNote}
              onChange={(e) => setDoctorNote(e.currentTarget.value)}
            />
          )}

          <Group justify="space-between">
            <Text size="xs" c="dimmed">
              Recorded under your name. It cannot be changed afterwards.
            </Text>
            <Button
              size="xs"
              color={choice === 'decline' ? 'red' : undefined}
              disabled={!ready}
              loading={submit.isPending}
              onClick={() => submit.mutate()}
            >
              {choice === 'doctor' ? 'Send to a doctor' : choice === 'decline' ? 'Decline' : 'Approve and issue the policy'}
            </Button>
          </Group>
        </Stack>
      )}
    </Stack>
  )
}

function Recorded({ data }: { data: ApplicationDetail }) {
  const d = data.decision!
  if (d.decision === 'declined') {
    return (
      <Alert color="red" variant="light" icon={<IconCircleX size={18} />} title="Declined">
        <Text size="sm">{d.declineReasonLabel ?? d.declineReason}</Text>
        {d.declineNote && (
          <Text size="xs" mt={4}>
            Note to the client: {d.declineNote}
          </Text>
        )}
        <Text size="xs" c="dimmed" mt={4}>
          {d.underwriterName ?? 'An underwriter'}, {day(d.decidedAt)}
          {d.reapplyAfter ? ` · may apply again from ${day(d.reapplyAfter)}` : ''}
        </Text>
      </Alert>
    )
  }
  return (
    <Alert color="teal" variant="light" icon={<IconCircleCheck size={18} />} title="Approved">
      <Text size="sm">
        {d.ratingPct ? `Rated +${d.ratingPct}%` : 'Standard rates'}
        {(d.exclusions ?? []).length ? `, ${(d.exclusions ?? []).length} exclusion${(d.exclusions ?? []).length === 1 ? '' : 's'}` : ''}
        {d.finalPremium != null ? ` · ${taka(d.finalPremium)} a month` : ''}
        {data.policy ? ` · policy ${data.policy.policyNumber}` : ''}
      </Text>
      <Text size="xs" c="dimmed" mt={4}>
        {d.underwriterName ?? 'An underwriter'}, {day(d.decidedAt)}. A recorded decision cannot be changed.
      </Text>
    </Alert>
  )
}
