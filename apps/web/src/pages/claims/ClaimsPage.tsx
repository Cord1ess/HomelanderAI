import {
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  Drawer,
  FileButton,
  Group,
  NumberInput,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconAlertTriangle, IconPaperclip } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import {
  addClaimDocuments,
  claimAction,
  claimDocumentUrl,
  getClaims,
  type Claim,
  type ClaimAction,
} from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { Stat } from '../../components/Stat'
import { EmptyState, ErrorState, LoadingState } from '../../components/states'
import { useAuth } from '../../context/AuthContext'

const taka = (v: string | number) => `৳${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
const day = (iso: string) =>
  new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })

const CLAIM_STATUS: Record<string, { label: string; color: string }> = {
  submitted: { label: 'New', color: 'blue' },
  documents_requested: { label: 'Waiting on documents', color: 'orange' },
  under_review: { label: 'Being reviewed', color: 'grape' },
  approved: { label: 'Approved, to be paid', color: 'teal' },
  rejected: { label: 'Rejected', color: 'red' },
  settled: { label: 'Paid', color: 'gray' },
}

/**
 * Claims: what has been claimed, what is waiting, and the legal clock. A claim
 * is settled within 90 days of its documents being complete (Insurance Act
 * 2010); the clock is shown on every open claim.
 */
export function ClaimsPage() {
  const [show, setShow] = useState<'open' | 'all'>('open')
  const [openId, setOpenId] = useState<string | null>(null)
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['claims', show],
    queryFn: () => getClaims(show === 'open' ? 'open' : undefined),
    refetchInterval: 60_000,
  })
  const { data: everything } = useQuery({ queryKey: ['claims', 'all'], queryFn: () => getClaims() })
  const all = everything ?? []
  const rows = data ?? []
  const opened = rows.find((c) => c.id === openId) ?? all.find((c) => c.id === openId) ?? null
  const isOpen = (c: Claim) => !['rejected', 'settled'].includes(c.status)

  return (
    <Stack gap="md">
      <PageHeader screen="claims">
        <SimpleGrid cols={{ base: 2, md: 5 }} spacing="xs">
          <Stat label="Open" value={all.filter(isOpen).length} color="blue" />
          <Stat
            label="Past 90 days"
            value={all.filter((c) => isOpen(c) && (c.daysLeft ?? 1) < 0).length}
            color="red"
            hint="The legal settlement date has passed"
          />
          <Stat label="Waiting on documents" value={all.filter((c) => c.status === 'documents_requested').length} color="orange" />
          <Stat
            label="Approved, to be paid"
            value={taka(all.filter((c) => c.status === 'approved').reduce((t, c) => t + Number(c.approvedAmountBdt ?? 0), 0))}
            color="teal"
          />
          <Stat
            label="Paid"
            value={taka(all.filter((c) => c.status === 'settled').reduce((t, c) => t + Number(c.approvedAmountBdt ?? 0), 0))}
          />
        </SimpleGrid>
      </PageHeader>

      <SegmentedControl
        size="xs"
        w={240}
        value={show}
        onChange={(v) => setShow(v as 'open' | 'all')}
        data={[
          { value: 'open', label: 'Open' },
          { value: 'all', label: 'All' },
        ]}
      />

      {isPending && <LoadingState label="Loading claims" />}
      {error && !data && <ErrorState title="Could not load the claims" error={error} retry={() => void refetch()} />}
      {data && (
        <Box style={{ border: '1px solid var(--neo-border-mid)', borderRadius: 'var(--mantine-radius-sm)', overflow: 'hidden' }}>
          <Table.ScrollContainer minWidth={900}>
            <Table highlightOnHover verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Claim</Table.Th>
                  <Table.Th>Client</Table.Th>
                  <Table.Th>What</Table.Th>
                  <Table.Th ta="right">Claimed</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Settle by</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={6} p={0}>
                      <EmptyState
                        title={show === 'open' ? 'No open claims' : 'No claims yet'}
                        text="Clients file hospital claims from their portal; death claims are filed from the client's policy."
                      />
                    </Table.Td>
                  </Table.Tr>
                )}
                {rows.map((c) => (
                  <Table.Tr key={c.id} className="queue-row" data-openable onClick={() => setOpenId(c.id)}>
                    <Table.Td>
                      <Text fz="sm" ff="monospace" fw={600}>
                        {c.claimNumber}
                      </Text>
                      <Text fz="xs" c="dimmed">
                        {c.filedByClient ? 'From the client' : 'Filed by staff'} · {day(c.createdAt)}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text fz="sm" fw={600}>
                        {c.clientName ?? '—'}
                      </Text>
                      <Text fz="xs" c="dimmed" ff="monospace">
                        {c.policyNumber}
                      </Text>
                    </Table.Td>
                    <Table.Td fz="sm">
                      {c.claimType === 'death' ? 'Death' : 'Hospital'} on {day(c.eventDate)}
                      {(c.checks ?? []).length > 0 && (
                        <Badge ml={6} size="xs" color="orange" variant="light">
                          {(c.checks ?? []).length} to check
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td ta="right" fz="sm" ff="monospace">
                      {taka(c.claimedAmountBdt)}
                    </Table.Td>
                    <Table.Td>
                      <Badge size="sm" variant="light" color={CLAIM_STATUS[c.status]?.color ?? 'gray'} style={{ minWidth: 'max-content' }}>
                        {CLAIM_STATUS[c.status]?.label ?? c.status}
                      </Badge>
                    </Table.Td>
                    <Table.Td fz="sm">
                      {c.settleBy ? (
                        <Text fz="sm" c={c.daysLeft != null && c.daysLeft < 0 ? 'red' : c.daysLeft != null && c.daysLeft <= 14 ? 'orange' : undefined}>
                          {day(c.settleBy)}
                          {c.daysLeft != null && (c.daysLeft < 0 ? ` · ${-c.daysLeft} days late` : ` · ${c.daysLeft} days left`)}
                        </Text>
                      ) : (
                        <Text fz="xs" c="dimmed">
                          Starts when documents are complete
                        </Text>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Box>
      )}

      <Drawer opened={Boolean(opened)} onClose={() => setOpenId(null)} position="right" size="lg" title={opened ? `Claim ${opened.claimNumber}` : ''}>
        {opened && <ClaimDetail claim={opened} />}
      </Drawer>
    </Stack>
  )
}

function ClaimDetail({ claim }: { claim: Claim }) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [note, setNote] = useState('')
  const [amount, setAmount] = useState<number | ''>(Number(claim.claimedAmountBdt))
  const [reference, setReference] = useState('')
  const open = !['rejected', 'settled'].includes(claim.status)

  const act = useMutation({
    mutationFn: (action: ClaimAction) =>
      claimAction(claim.id, {
        action,
        note: note.trim() || null,
        approvedAmountBdt: action === 'approve' ? Number(amount) || null : null,
        settlementReference: action === 'settle' ? reference.trim() || null : null,
      }),
    onSuccess: (c) => {
      void queryClient.invalidateQueries({ queryKey: ['claims'] })
      setNote('')
      notifications.show({ title: CLAIM_STATUS[c.status]?.label ?? 'Updated', message: `Claim ${c.claimNumber}`, color: 'teal' })
    },
    onError: (e) => notifications.show({ title: 'Could not do that', message: (e as Error).message, color: 'red' }),
  })
  const attach = useMutation({
    mutationFn: (files: File[]) => addClaimDocuments(claim.id, files),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['claims'] }),
    onError: (e) => notifications.show({ title: 'Could not attach', message: (e as Error).message, color: 'red' }),
  })

  return (
    <Stack gap="md">
      <Group gap="xs">
        <Badge variant="light" color={CLAIM_STATUS[claim.status]?.color ?? 'gray'}>
          {CLAIM_STATUS[claim.status]?.label ?? claim.status}
        </Badge>
        <Anchor component={Link} to={`/clients/${claim.clientId}`} size="sm">
          {claim.clientName} · {claim.clientReference}
        </Anchor>
      </Group>
      <SimpleGrid cols={2} spacing="sm">
        <Field label={claim.claimType === 'death' ? 'Date of death' : 'Date admitted'} value={day(claim.eventDate)} />
        <Field label="Claimed" value={taka(claim.claimedAmountBdt)} />
        <Field label="Policy pays at most" value={claim.payableLimitBdt != null ? taka(claim.payableLimitBdt) : '—'} />
        <Field label="Settle by" value={claim.settleBy ? day(claim.settleBy) : 'When documents are complete'} />
        {claim.hospital && <Field label="Hospital" value={claim.hospital} />}
        {claim.claimantName && <Field label="Claimant" value={claim.claimantName} />}
      </SimpleGrid>
      <Text size="sm">{claim.description}</Text>

      {(claim.checks ?? []).length > 0 && (
        <Alert color="orange" variant="light" icon={<IconAlertTriangle size={16} />} title="Check before deciding">
          <Stack gap={4}>
            {(claim.checks ?? []).map((c) => (
              <Text key={c} size="sm">
                {c}
              </Text>
            ))}
          </Stack>
        </Alert>
      )}

      <div>
        <Group justify="space-between" mb={4}>
          <Text size="sm" fw={700}>
            Documents
          </Text>
          {open && (
            <FileButton multiple accept="application/pdf,image/png,image/jpeg" onChange={(f) => f.length && attach.mutate(f)}>
              {(props) => (
                <Button {...props} size="compact-xs" variant="subtle" leftSection={<IconPaperclip size={12} />} loading={attach.isPending}>
                  Attach
                </Button>
              )}
            </FileButton>
          )}
        </Group>
        {(claim.documents ?? []).length === 0 ? (
          <Text size="xs" c="dimmed">
            None yet.
          </Text>
        ) : (
          <Stack gap={2}>
            {(claim.documents ?? []).map((d) => (
              <Anchor key={d.id} href={claimDocumentUrl(claim.id, d.id)} target="_blank" size="sm">
                {d.fileName ?? 'Document'}
                <Text span size="xs" c="dimmed">
                  {' '}
                  · {d.uploadedByClient ? 'from the client' : 'from staff'}, {day(d.createdAt)}
                </Text>
              </Anchor>
            ))}
          </Stack>
        )}
        {claim.documentsNote && (
          <Text size="xs" c="orange" mt={4}>
            Asked for: {claim.documentsNote}
          </Text>
        )}
      </div>

      {claim.decisionNote && (
        <Alert color={claim.status === 'rejected' ? 'red' : 'teal'} variant="light" p="xs">
          <Text size="sm">{claim.decisionNote}</Text>
          <Text size="xs" c="dimmed">
            {claim.decidedByName ?? 'Staff'}
            {claim.decidedAt ? `, ${day(claim.decidedAt)}` : ''}
          </Text>
        </Alert>
      )}
      {claim.status === 'settled' && (
        <Alert color="gray" variant="light" p="xs">
          <Text size="sm">
            Paid {taka(claim.approvedAmountBdt ?? 0)} on {claim.settledAt ? day(claim.settledAt) : '—'}
            {claim.settlementReference ? ` · bank reference ${claim.settlementReference}` : ''}
          </Text>
        </Alert>
      )}

      {open && claim.status !== 'approved' && (
        <Stack gap="xs">
          <Textarea
            label="Note"
            description="Which documents you need, or why it is rejected. The client reads it."
            autosize
            minRows={2}
            value={note}
            onChange={(e) => setNote(e.currentTarget.value)}
          />
          <Group gap="xs">
            <Button size="xs" variant="light" color="orange" disabled={!note.trim()} loading={act.isPending && act.variables === 'request_documents'} onClick={() => act.mutate('request_documents')}>
              Ask for documents
            </Button>
            {!claim.documentsCompleteAt && (
              <Button size="xs" variant="light" loading={act.isPending && act.variables === 'documents_complete'} onClick={() => act.mutate('documents_complete')}>
                Documents complete: start the 90 days
              </Button>
            )}
            <Button size="xs" variant="light" color="red" disabled={!note.trim()} loading={act.isPending && act.variables === 'reject'} onClick={() => act.mutate('reject')}>
              Reject
            </Button>
          </Group>
          <Group gap="xs" align="flex-end">
            <NumberInput size="xs" label="Approve for (BDT)" thousandSeparator="," min={1} value={amount} onChange={(v) => setAmount(v === '' ? '' : Number(v))} w={200} />
            <Button size="xs" color="teal" disabled={!amount} loading={act.isPending && act.variables === 'approve'} onClick={() => act.mutate('approve')}>
              Approve
            </Button>
          </Group>
        </Stack>
      )}
      {claim.status === 'approved' && user?.role === 'admin' && (
        <Group gap="xs" align="flex-end">
          <TextInput size="xs" label="Bank reference" placeholder="From the bank's payment advice" value={reference} onChange={(e) => setReference(e.currentTarget.value)} w={240} />
          <Button size="xs" loading={act.isPending} onClick={() => act.mutate('settle')}>
            Record that the bank has paid
          </Button>
        </Group>
      )}
      {claim.status === 'approved' && user?.role !== 'admin' && (
        <Text size="xs" c="dimmed">
          Approved. The bank pays it; an administrator records the payment here.
        </Text>
      )}
    </Stack>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.4}>
        {label}
      </Text>
      <Text size="sm" fw={600}>
        {value}
      </Text>
    </div>
  )
}
