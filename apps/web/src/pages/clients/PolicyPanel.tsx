import {
  Alert,
  Badge,
  Button,
  Group,
  Modal,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconCash, IconCircleX } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { cancelPolicy, recordPayment, type PaymentMethod, type Policy } from '../../api/client'
import { useAuth } from '../../context/AuthContext'

const taka = (v: string | number) => `৳${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
const day = (iso: string) =>
  new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })

const METHODS: { value: PaymentMethod; label: string }[] = [
  { value: 'bkash', label: 'bKash' },
  { value: 'nagad', label: 'Nagad' },
  { value: 'rocket', label: 'Rocket' },
  { value: 'bank', label: 'Bank transfer' },
  { value: 'card', label: 'Card' },
  { value: 'cash', label: 'Cash at the office' },
]

const STATUS: Record<string, { label: string; color: string }> = {
  paid: { label: 'Paid', color: 'teal' },
  due: { label: 'Due now', color: 'yellow' },
  overdue: { label: 'Overdue', color: 'red' },
  upcoming: { label: 'Coming up', color: 'gray' },
}

/**
 * A client's policies: what each pays out and costs, its payments, and, for
 * the company owner, recording a payment or cancelling it.
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
  const queryClient = useQueryClient()
  const [method, setMethod] = useState<PaymentMethod>('bkash')
  const [reference, setReference] = useState('')
  const [cancelling, setCancelling] = useState(false)
  const [reason, setReason] = useState('')
  const active = policy.status === 'active'

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['client', clientId] })
    void queryClient.invalidateQueries({ queryKey: ['analytics'] })
    void queryClient.invalidateQueries({ queryKey: ['applications'] })
    void queryClient.invalidateQueries({ queryKey: ['application', policy.applicationId] })
  }

  const pay = useMutation({
    mutationFn: () => recordPayment(policy.id, { method, reference: reference.trim() || null }),
    onSuccess: (p) => {
      refresh()
      setReference('')
      notifications.show({
        title: 'Payment recorded',
        message: `${p.paidCount} of ${p.monthsTotal} months paid. The client sees it on their portal.`,
        color: 'teal',
      })
    },
    onError: (e) => notifications.show({ title: 'Could not record it', message: (e as Error).message, color: 'red' }),
  })

  const cancel = useMutation({
    mutationFn: () => cancelPolicy(policy.id, reason.trim()),
    onSuccess: () => {
      refresh()
      setCancelling(false)
      setReason('')
      notifications.show({
        title: 'Policy cancelled',
        message: 'No more payments fall due. The client sees it on their portal.',
        color: 'gray',
      })
    },
    onError: (e) => notifications.show({ title: 'Could not cancel', message: (e as Error).message, color: 'red' }),
  })

  const installments = [...(policy.installments ?? [])].reverse().slice(0, 8)

  return (
    <Paper p="md" bd={`1px solid ${active ? 'var(--neo-forest)' : 'var(--neo-border-mid)'}`}>
      <Group justify="space-between" align="flex-start" mb="sm">
        <div>
          <Group gap="xs">
            <Text fw={700}>Policy {policy.policyNumber}</Text>
            <Badge color={active ? 'teal' : 'red'} variant="light" style={{ minWidth: 'max-content' }}>
              {active ? 'In force' : 'Cancelled'}
            </Badge>
            {(policy.overdueCount ?? 0) > 0 && active && (
              <Badge color="red" variant="filled">
                {policy.overdueCount} overdue
              </Badge>
            )}
          </Group>
          <Text size="xs" c="dimmed">
            {policy.planName}
            {policy.coverageType ? ` · ${policy.coverageType} cover` : ''} · {day(policy.startDate)} to{' '}
            {day(policy.endDate)} ({policy.termYears} years)
          </Text>
        </div>
        {isOwner && active && (
          <Button size="xs" color="red" variant="light" leftSection={<IconCircleX size={14} />} onClick={() => setCancelling(true)}>
            Cancel this policy
          </Button>
        )}
      </Group>

      {!active && (
        <Alert color="red" variant="light" mb="sm" p="xs">
          <Text size="sm">
            Cancelled {policy.cancelledAt ? day(policy.cancelledAt) : ''}
            {policy.cancelledByName ? ` by ${policy.cancelledByName}` : ''}. Reason: {policy.cancelReason ?? '—'}
          </Text>
        </Alert>
      )}

      <SimpleGrid cols={compact ? 2 : { base: 2, md: 5 }} spacing="md">
        <Figure label="Pays out on a claim" value={taka(policy.sumAssuredBdt)} strong />
        <Figure label="Premium" value={`${taka(policy.monthlyPremiumBdt)} / month`} />
        <Figure label="Per year" value={taka(policy.yearlyPremiumBdt)} />
        <Figure label="Paid so far" value={`${policy.paidCount} of ${policy.monthsTotal} · ${taka(policy.paidTotalBdt ?? 0)}`} />
        <Figure
          label="Next due"
          value={active && policy.nextDue ? `${day(policy.nextDue)} · ${taka(policy.nextAmountBdt ?? policy.monthlyPremiumBdt)}` : '—'}
        />
      </SimpleGrid>

      {isOwner && active && policy.nextDue && (
        <Group mt="md" gap="xs" align="flex-end">
          <Select
            size="xs"
            label="Record the next payment"
            data={METHODS}
            value={method}
            onChange={(v) => v && setMethod(v as PaymentMethod)}
            allowDeselect={false}
            w={180}
          />
          <TextInput
            size="xs"
            label="Transaction reference"
            placeholder="Optional, e.g. bKash TrxID"
            value={reference}
            onChange={(e) => setReference(e.currentTarget.value)}
            w={220}
          />
          <Button size="xs" leftSection={<IconCash size={14} />} loading={pay.isPending} onClick={() => pay.mutate()}>
            Mark {day(policy.nextDue)} as paid
          </Button>
        </Group>
      )}

      {installments.length > 0 && (
        <Table mt="md" verticalSpacing={4} fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>#</Table.Th>
              <Table.Th>Due</Table.Th>
              <Table.Th>Amount</Table.Th>
              <Table.Th>Status</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {installments.map((i) => (
              <Table.Tr key={i.dueDate}>
                <Table.Td>{i.number}</Table.Td>
                <Table.Td>{day(i.dueDate)}</Table.Td>
                <Table.Td ff="monospace">{taka(i.amountBdt)}</Table.Td>
                <Table.Td>
                  <Badge size="sm" variant="light" color={STATUS[i.status]?.color ?? 'gray'} style={{ minWidth: 'max-content' }}>
                    {STATUS[i.status]?.label ?? i.status}
                    {i.status === 'paid' && i.paidOn ? ` ${day(i.paidOn)}` : ''}
                    {i.status === 'paid' && i.method ? ` · ${METHODS.find((m) => m.value === i.method)?.label ?? i.method}` : ''}
                  </Badge>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Modal opened={cancelling} onClose={() => setCancelling(false)} title={`Cancel policy ${policy.policyNumber}?`} centered>
        <Stack gap="sm">
          <Text size="sm">
            The client stops being covered and no more payments fall due. They see the cancellation, and your reason,
            on their portal. This cannot be undone.
          </Text>
          <Textarea
            label="Reason"
            placeholder="For example: the client asked to cancel; premiums unpaid for three months."
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
