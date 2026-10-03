import {
  Alert,
  Anchor,
  Badge,
  Button,
  Group,
  List,
  Modal,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconCircleX, IconFileDollar } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { cancelPolicy, type Policy } from '../../api/client'
import { useAuth } from '../../context/AuthContext'
import { ClaimForm } from '../claims/ClaimForm'

const taka = (v: string | number) => `৳${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
const day = (iso: string) =>
  new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })

const STATE: Record<string, { label: string; color: string }> = {
  active: { label: 'In force', color: 'teal' },
  cancelled: { label: 'Cancelled', color: 'red' },
  expired: { label: 'Ended', color: 'gray' },
}

/**
 * A client's policies: what each pays out and costs, its dates, what it does
 * not cover; filing a claim on it; and, for the owner, cancelling it.
 * Premiums are collected by the bank, so this shows when they fall due only.
 */
export function PolicyPanel({
  policies,
  clientId,
  compact = false,
}: {
  policies: Policy[]
  clientId: string
  /** For a narrow column: figures two to a row. */
  compact?: boolean
}) {
  return (
    <Stack gap="md">
      {policies.map((p) => (
        <OnePolicy key={p.id} policy={p} clientId={clientId} compact={compact} />
      ))}
    </Stack>
  )
}

function OnePolicy({ policy, clientId, compact }: { policy: Policy; clientId: string; compact: boolean }) {
  const { user } = useAuth()
  const isOwner = user?.role === 'admin'
  const canClaim = user?.role === 'admin' || user?.role === 'underwriter'
  const queryClient = useQueryClient()
  const [cancelling, setCancelling] = useState(false)
  const [claiming, setClaiming] = useState(false)
  const [reason, setReason] = useState('')
  const state = STATE[policy.effectiveStatus] ?? STATE.active
  const active = policy.effectiveStatus === 'active'
  const health = policy.product === 'health'

  const cancel = useMutation({
    mutationFn: () => cancelPolicy(policy.id, reason.trim()),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['client', clientId] })
      void queryClient.invalidateQueries({ queryKey: ['application', policy.applicationId] })
      void queryClient.invalidateQueries({ queryKey: ['analytics'] })
      void queryClient.invalidateQueries({ queryKey: ['applications'] })
      setCancelling(false)
      setReason('')
      notifications.show({
        title: 'Policy cancelled',
        message: 'No more premiums fall due. The client sees it on their portal.',
        color: 'gray',
      })
    },
    onError: (e) => notifications.show({ title: 'Could not cancel', message: (e as Error).message, color: 'red' }),
  })

  return (
    <Paper p="md" bd={`1px solid ${active ? 'var(--neo-forest)' : 'var(--neo-border-mid)'}`}>
      <Group justify="space-between" align="flex-start" mb="sm" gap="xs">
        <div>
          <Group gap="xs">
            <Text fw={700}>Policy {policy.policyNumber}</Text>
            <Badge color={state.color} variant="light" style={{ minWidth: 'max-content' }}>
              {state.label}
            </Badge>
            {policy.inFreeLook && (
              <Badge color="blue" variant="light" style={{ minWidth: 'max-content' }}>
                Free look until {day(policy.freeLookUntil!)}
              </Badge>
            )}
            {policy.renewalDue && (
              <Badge color="orange" variant="light" style={{ minWidth: 'max-content' }}>
                Renewal due
              </Badge>
            )}
          </Group>
          <Text size="xs" c="dimmed">
            {policy.planName} · {day(policy.startDate)} to {day(policy.endDate)}
            {health ? ' (renewed yearly)' : ` (${policy.termYears} years)`}
          </Text>
        </div>
        <Group gap="xs">
          {canClaim && policy.effectiveStatus !== 'cancelled' && (
            <Button size="xs" variant="light" leftSection={<IconFileDollar size={14} />} onClick={() => setClaiming(true)}>
              File a claim
            </Button>
          )}
          {isOwner && active && (
            <Button size="xs" color="red" variant="light" leftSection={<IconCircleX size={14} />} onClick={() => setCancelling(true)}>
              Cancel
            </Button>
          )}
        </Group>
      </Group>

      {policy.effectiveStatus === 'cancelled' && (
        <Alert color="red" variant="light" mb="sm" p="xs">
          <Text size="sm">
            Cancelled {policy.cancelledAt ? day(policy.cancelledAt) : ''}
            {policy.cancelledByName ? ` by ${policy.cancelledByName}` : ''}. Reason: {policy.cancelReason ?? '—'}
          </Text>
        </Alert>
      )}

      <SimpleGrid cols={compact ? 2 : { base: 2, md: 5 }} spacing="md">
        <Figure label={health ? 'Pays in a year, at most' : 'Pays out on a claim'} value={taka(policy.sumAssuredBdt)} strong />
        <Figure
          label={`Premium (${policy.premiumMode === 'yearly' ? 'yearly' : 'monthly'})`}
          value={`${taka(policy.premiumAmountBdt)}${policy.premiumMode === 'yearly' ? ' / year' : ' / month'}`}
        />
        <Figure label="Per year" value={taka(policy.annualPremiumBdt)} />
        <Figure label="Next premium due" value={policy.nextPremiumDue ? day(policy.nextPremiumDue) : '—'} />
        {health ? (
          <Figure label="Left this year" value={policy.remainingLimitBdt != null ? taka(policy.remainingLimitBdt) : '—'} />
        ) : (
          <Figure label="Rating" value={policy.ratingPct ? `+${policy.ratingPct}%` : 'Standard'} />
        )}
      </SimpleGrid>

      {health && (policy.waitingUntil || policy.preexistingUntil) && (
        <Text size="xs" c="dimmed" mt="sm">
          Illness covered from {policy.waitingUntil ? day(policy.waitingUntil) : 'the start'} (accidents from day one);
          conditions the client already had from {policy.preexistingUntil ? day(policy.preexistingUntil) : '—'}.
        </Text>
      )}
      {(policy.exclusions ?? []).length > 0 && (
        <Stack gap={2} mt="sm">
          <Text size="xs" fw={700} c="dimmed" tt="uppercase">
            Not covered
          </Text>
          <List size="xs" spacing={2}>
            {(policy.exclusions ?? []).map((e) => (
              <List.Item key={e}>{e}</List.Item>
            ))}
          </List>
        </Stack>
      )}
      <Group gap="md" mt="sm">
        <Text size="xs" c="dimmed">
          Premiums are collected by the bank.
        </Text>
        {(policy.claimsOpen ?? 0) > 0 && (
          <Anchor component={Link} to="/claims" size="xs">
            {policy.claimsOpen} open claim{policy.claimsOpen === 1 ? '' : 's'}
          </Anchor>
        )}
        {Number(policy.claimsPaidBdt ?? 0) > 0 && (
          <Text size="xs" c="dimmed">
            {taka(policy.claimsPaidBdt ?? 0)} paid in claims
          </Text>
        )}
      </Group>

      <ClaimForm policy={policy} opened={claiming} onClose={() => setClaiming(false)} />
      <Modal opened={cancelling} onClose={() => setCancelling(false)} title={`Cancel policy ${policy.policyNumber}?`} centered>
        <Stack gap="sm">
          <Text size="sm">
            {policy.inFreeLook
              ? 'This is within the free-look period: the client is owed a full refund of what they paid, through the bank.'
              : 'The client stops being covered and no more premiums fall due.'}{' '}
            They see the cancellation, and your reason, on their portal. This cannot be undone.
          </Text>
          <Textarea
            label="Reason"
            placeholder="For example: the client asked to cancel within the free-look period."
            autosize
            minRows={3}
            value={reason}
            onChange={(e) => setReason(e.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="default" size="xs" onClick={() => setCancelling(false)}>
              Keep the policy
            </Button>
            <Button color="red" size="xs" loading={cancel.isPending} disabled={reason.trim().length < 5} onClick={() => cancel.mutate()}>
              Cancel the policy
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Paper>
  )
}

function Figure({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.4}>
        {label}
      </Text>
      <Text size={strong ? 'lg' : 'sm'} fw={700} mt={2}>
        {value}
      </Text>
    </div>
  )
}
