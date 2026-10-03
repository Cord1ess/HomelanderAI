import { Button, Checkbox, FileButton, Group, Modal, NumberInput, Stack, Text, TextInput, Textarea } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconPaperclip } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { fileClaim, type Policy } from '../../api/client'

const taka = (v: string | number) => `৳${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

/**
 * Staff filing a claim for someone: a death claim brought by the nominee to the
 * office, or hospital bills a client could not upload themselves.
 */
export function ClaimForm({ policy, opened, onClose }: { policy: Policy; opened: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const life = policy.product === 'life'
  const [eventDate, setEventDate] = useState(new Date().toISOString().slice(0, 10))
  const [amount, setAmount] = useState<number | ''>(life ? Number(policy.sumAssuredBdt) : '')
  const [description, setDescription] = useState('')
  const [hospital, setHospital] = useState('')
  const [claimant, setClaimant] = useState('')
  const [accident, setAccident] = useState(false)
  const [files, setFiles] = useState<File[]>([])

  const file = useMutation({
    mutationFn: () =>
      fileClaim(
        policy.id,
        {
          eventDate,
          claimedAmountBdt: Number(amount),
          description: description.trim(),
          hospital: hospital.trim() || null,
          claimantName: claimant.trim() || null,
          accident,
        },
        files,
      ),
    onSuccess: (claim) => {
      void queryClient.invalidateQueries({ queryKey: ['claims'] })
      void queryClient.invalidateQueries({ queryKey: ['client', policy.clientId] })
      void queryClient.invalidateQueries({ queryKey: ['application', policy.applicationId] })
      notifications.show({ title: `Claim ${claim.claimNumber} filed`, message: 'It is on the Claims page.', color: 'teal' })
      onClose()
    },
    onError: (e) => notifications.show({ title: 'Could not file the claim', message: (e as Error).message, color: 'red' }),
  })

  return (
    <Modal opened={opened} onClose={onClose} title={`File a claim on ${policy.policyNumber}`} centered size="lg">
      <Stack gap="sm">
        <Text size="sm" c="dimmed">
          {life
            ? `A death claim pays the sum assured, ${taka(policy.sumAssuredBdt)}, to the nominee. Attach the death certificate and the nominee's NID.`
            : `Hospital bills, up to what is left of this year's limit (${taka(policy.remainingLimitBdt ?? policy.sumAssuredBdt)}). Attach the bills and the discharge summary.`}
        </Text>
        <Group grow>
          <TextInput label={life ? 'Date of death' : 'Date admitted'} type="date" value={eventDate} onChange={(e) => setEventDate(e.currentTarget.value)} />
          <NumberInput label="Amount claimed (BDT)" thousandSeparator="," min={1} value={amount} onChange={(v) => setAmount(v === '' ? '' : Number(v))} />
        </Group>
        {life ? (
          <TextInput label="Claimant (the nominee)" value={claimant} onChange={(e) => setClaimant(e.currentTarget.value)} />
        ) : (
          <Group grow align="flex-end">
            <TextInput label="Hospital" value={hospital} onChange={(e) => setHospital(e.currentTarget.value)} />
            <Checkbox label="This was an accident" checked={accident} onChange={(e) => setAccident(e.currentTarget.checked)} mb={8} />
          </Group>
        )}
        <Textarea label="What happened" autosize minRows={3} value={description} onChange={(e) => setDescription(e.currentTarget.value)} />
        <Group justify="space-between">
          <FileButton multiple accept="application/pdf,image/png,image/jpeg" onChange={setFiles}>
            {(props) => (
              <Button {...props} size="xs" variant="default" leftSection={<IconPaperclip size={14} />}>
                {files.length ? `${files.length} document${files.length === 1 ? '' : 's'} attached` : 'Attach documents'}
              </Button>
            )}
          </FileButton>
          <Button
            onClick={() => file.mutate()}
            loading={file.isPending}
            disabled={!eventDate || !amount || description.trim().length < 5}
          >
            File the claim
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
