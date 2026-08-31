import {
  Box,
  Button,
  Checkbox,
  Divider,
  Group,
  NumberInput,
  Paper,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Alert,
  Loader,
} from '@mantine/core'
import { Dropzone, IMAGE_MIME_TYPE } from '@mantine/dropzone'
import { useForm } from '@mantine/form'
import { IconAlertCircle, IconCircleCheck, IconFileUpload } from '@tabler/icons-react'
import { useState } from 'react'

import { Section } from './components'

/**
 * Intake form — data entry with the client sitting opposite.
 *
 * ONE scrolling page with sections, submitted once at the end. Not a wizard:
 * operators jump around and clients correct themselves, so nothing may be lost
 * between steps. A sticky "n/4 sections complete" hint, one submit.
 *
 * Section completeness is derived from form state, not hardcoded:
 *   1 · Applicant   → reference set
 *   2 · Coverage    → type + amount set
 *   3 · Health      → "Previously treated for TB" answered and, when yes, the
 *                     follow-up "Completed the full course" also answered.
 *   4 · Evidence    → at least one chest X-ray attached
 *
 * Submit stays disabled until reference + coverage type/amount + ≥1 X-ray.
 *
 * TODO: `POST /api/applications` as `multipart/form-data` in one request; real
 * progress during upload; confirmation panel persists after success.
 */

interface IntakeForm {
  reference: string
  dob: string
  sex: string | null
  coverageType: string | null
  coverageAmount: number | null
  previouslyTreatedForTb: boolean
  completedTreatment: boolean
  symptoms: string[]
  history: string[]
}

interface EvidenceFile {
  id: string
  name: string
  size: number
  fileType: string
}

const SYMPTOMS = [
  'Cough lasting more than 2 weeks',
  'Unexplained weight loss',
  'Night sweats',
  'Coughing up blood',
  'Fever',
]

const HISTORY_ONCE = [
  'Diabetes',
  'HIV positive',
  'Someone in the household has had TB',
  'Took a course of antibiotics without improvement',
  'Current or former smoker',
]

const FILE_TYPES = ['Chest X-ray', 'Lab report', 'Clinical note']
const MAX_FILE_BYTES = 50 * 1024 * 1024

function formatSize(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

export function IntakePage() {
  const form = useForm<IntakeForm>({
    initialValues: {
      reference: '',
      dob: '',
      sex: null,
      coverageType: null,
      coverageAmount: null,
      previouslyTreatedForTb: false,
      completedTreatment: false,
      symptoms: [],
      history: [],
    },
  })

  const [files, setFiles] = useState<EvidenceFile[]>([])
  const [rejectNote, setRejectNote] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const toggleSet = (key: 'symptoms' | 'history', value: string) =>
    form.setFieldValue(
      key,
      form.values[key].includes(value)
        ? form.values[key].filter((v) => v !== value)
        : [...form.values[key], value],
    )

  const onDrop = (dropped: File[]) => {
    setRejectNote(null)
    const accepted: EvidenceFile[] = []
    for (const f of dropped) {
      accepted.push({
        id: crypto.randomUUID(),
        name: f.name,
        size: f.size,
        fileType: 'Chest X-ray',
      })
    }
    setFiles((prev) => [...prev, ...accepted])
  }

  const onReject = (rejects: { file: File }[]) => {
    const tooBig = rejects.some((r) => r.file.size > MAX_FILE_BYTES)
    setRejectNote(
      tooBig
        ? 'One or more files were rejected — files over 50 MB are not accepted.'
        : 'One or more files were rejected. Chest X-rays must be .dcm, .png, or .jpg.',
    )
  }

  const removeFile = (id: string) => setFiles((prev) => prev.filter((f) => f.id !== id))

  const hasXray = files.some((f) => f.fileType === 'Chest X-ray')

  const sections = [
    Boolean(form.values.reference.trim()),
    Boolean(form.values.coverageType) && (form.values.coverageAmount ?? 0) > 0,
    form.values.previouslyTreatedForTb
      ? form.values.completedTreatment
      : true,
    hasXray,
  ]
  const completeCount = sections.filter(Boolean).length

  const canSubmit =
    Boolean(form.values.reference.trim()) &&
    Boolean(form.values.coverageType) &&
    (form.values.coverageAmount ?? 0) > 0 &&
    hasXray

  const handleSubmit = () => {
    if (!canSubmit) return
    setSubmitting(true)
    // TODO: POST /api/applications (multipart), then navigate to the queue.
    window.setTimeout(() => {
      setSubmitting(false)
      setSubmitted(true)
    }, 1200)
  }

  if (submitted) {
    return (
      <Stack gap="md" maw={560}>
        <Alert
          icon={<IconCircleCheck size={18} />}
          color="teal"
          title="Application submitted"
        >
          <Text size="sm">
            Reference <Text span ff="monospace" fw={600}>{form.values.reference}</Text>{' '}
            is now in the queue as “Evaluation pending”.
          </Text>
        </Alert>
        <Button size="xs" onClick={() => { window.history.back() }}>
          Back to queue
        </Button>
      </Stack>
    )
  }

  return (
    <Stack gap="lg" maw={820}>
      {/* Sticky progress hint */}
      <Paper
        p="sm"
        pos="sticky"
        top={0}
        style={{ zIndex: 10 }}
        bd="1px solid var(--mantine-color-default-border)"
        bg="var(--mantine-color-body)"
      >
        <Group justify="space-between">
          <Text size="xs" c="dimmed">
            {completeCount} of 4 sections complete
          </Text>
          <Text size="xs" fw={600} c={canSubmit ? 'teal' : 'dimmed'}>
            {canSubmit ? 'Ready to submit' : 'Not ready to submit'}
          </Text>
        </Group>
      </Paper>

      <div>
        <Text size="xs" c="dimmed" tt="uppercase" fw={600} className="hl-eyebrow">
          New application
        </Text>
        <Text size="lg" fw={600}>
          Review a new client
        </Text>
        <Text size="sm" c="dimmed">
          Fill this out while the client is in front of you. One page, one submit.
        </Text>
      </div>

      {/* ── Section 1 · Applicant ─────────────────────────────── */}
      <Section
        n="1"
        title="Applicant"
        complete={sections[0]}
      >
        <TextInput
          label="Reference"
          description="The carrier's own client ID. Must be unique per tenant."
          required
          placeholder="ABC-12345"
          {...form.getInputProps('reference')}
        />
        <Group align="flex-end">
          <TextInput
            label="Date of birth"
            type="date"
            {...form.getInputProps('dob')}
          />
          <Select
            label="Sex"
            placeholder="Prefer not to say"
            data={['Female', 'Male', 'Other', 'Prefer not to say']}
            clearable
            {...form.getInputProps('sex')}
          />
        </Group>
      </Section>

      <Divider my="xs" />

      {/* ── Section 2 · Coverage requested ─────────────────────── */}
      <Section
        n="2"
        title="Coverage requested"
        complete={sections[1]}
      >
        <Group align="flex-end">
          <Select
            label="Coverage type"
            placeholder="Select"
            required
            data={['Life', 'Health', 'Critical illness']}
            {...form.getInputProps('coverageType')}
          />
          <NumberInput
            label="Coverage amount (BDT)"
            placeholder="1,000,000"
            required
            thousandSeparator=","
            min={0}
            {...form.getInputProps('coverageAmount')}
          />
        </Group>
      </Section>

      <Divider my="xs" />

      {/* ── Section 3 · Declared health ────────────────────────── */}
      <Section
        n="3"
        title="Declared health"
        complete={sections[2]}
      >
        <Text size="sm" c="dimmed">
          The client answers, you tick. These directly drive the risk score, so
          the wording is kept plain enough to read aloud.
        </Text>

        <Paper bd="1px solid var(--mantine-color-default-border)" p="md">
          <Text fw={600} size="sm" mb="sm">
            Current symptoms
          </Text>
          <Stack gap="xs">
            {SYMPTOMS.map((s) => (
              <Checkbox
                key={s}
                label={s}
                checked={form.values.symptoms.includes(s)}
                onChange={() => toggleSet('symptoms', s)}
              />
            ))}
          </Stack>
        </Paper>

        <Paper bd="1px solid var(--mantine-color-default-border)" p="md">
          <Text fw={600} size="sm" mb="sm">
            Medical history
          </Text>
          <Stack gap="xs">
            <Checkbox
              label="Previously treated for TB"
              checked={form.values.previouslyTreatedForTb}
              onChange={(e) =>
                form.setFieldValue('previouslyTreatedForTb', e.currentTarget.checked)
              }
            />
            {form.values.previouslyTreatedForTb && (
              <Box pl="lg">
                <Checkbox
                  label="Completed the full course of treatment"
                  checked={form.values.completedTreatment}
                  onChange={(e) =>
                    form.setFieldValue('completedTreatment', e.currentTarget.checked)
                  }
                />
              </Box>
            )}
            {HISTORY_ONCE.map((h) => (
              <Checkbox
                key={h}
                label={h}
                checked={form.values.history.includes(h)}
                onChange={() => toggleSet('history', h)}
              />
            ))}
          </Stack>
        </Paper>

        <Text size="xs" c="dimmed">
          TODO: post the nested JSON shape defined in DATABASE.md §C. The
          “Completed the full course of treatment” checkbox appears only when
          “Previously treated for TB” is ticked — this pair flips the outcome.
        </Text>
      </Section>

      <Divider my="xs" />

      {/* ── Section 4 · Evidence ───────────────────────────────── */}
      <Section
        n="4"
        title="Evidence"
        complete={sections[3]}
      >
        <DropShell onDrop={onDrop} onReject={onReject} />

        {rejectNote && (
          <Alert color="red" variant="light" icon={<IconAlertCircle size={16} />}>
            <Text size="sm">{rejectNote}</Text>
          </Alert>
        )}

        {files.length > 0 && (
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>File</Table.Th>
                <Table.Th>Size</Table.Th>
                <Table.Th>Type</Table.Th>
                <Table.Th w={60} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {files.map((f) => (
                <Table.Tr key={f.id}>
                  <Table.Td ff="monospace">{f.name}</Table.Td>
                  <Table.Td>{formatSize(f.size)}</Table.Td>
                  <Table.Td>
                    <Select
                      data={FILE_TYPES}
                      value={f.fileType}
                      onChange={(v) =>
                        setFiles((prev) =>
                          prev.map((x) =>
                            x.id === f.id ? { ...x, fileType: v ?? 'Chest X-ray' } : x,
                          ),
                        )
                      }
                      size="xs"
                    />
                  </Table.Td>
                  <Table.Td>
                    <Button
                      size="xs"
                      variant="subtle"
                      color="red"
                      onClick={() => removeFile(f.id)}
                    >
                      Remove
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}

        <Text size="xs" c="dimmed">
          In Phase 1 only the chest X-ray is analysed. Lab reports and clinical
          notes are stored only — they are not read by the model.
        </Text>
      </Section>

      <Divider my="xs" />

      <Group justify="space-between" align="flex-start">
        <Text size="xs" c="dimmed" maw={380}>
          Disabled until reference, coverage type and amount are filled, and at
          least one chest X-ray is attached.
        </Text>
        <Button
          size="sm"
          disabled={!canSubmit}
          loading={submitting}
          onClick={handleSubmit}
        >
          Submit application
        </Button>
      </Group>
      {submitting && (
        <Group gap="xs" c="dimmed">
          <Loader size={14} />
          <Text size="xs">Uploading evidence and creating the application…</Text>
        </Group>
      )}
    </Stack>
  )
}

function DropShell({
  onDrop,
  onReject,
}: {
  onDrop: (files: File[]) => void
  onReject: (files: { file: File }[]) => void
}) {
  return (
    <Dropzone
      onDrop={onDrop}
      onReject={onReject}
      accept={IMAGE_MIME_TYPE}
      maxSize={MAX_FILE_BYTES}
      multiple
    >
      <Group justify="center" gap="xl" py="md" style={{ pointerEvents: 'none' }}>
        <Dropzone.Accept>
          <IconFileUpload size={28} color="var(--mantine-color-clinical-5)" />
        </Dropzone.Accept>
        <Dropzone.Reject>
          <IconAlertCircle size={28} color="var(--mantine-color-red-5)" />
        </Dropzone.Reject>
        <Dropzone.Idle>
          <IconFileUpload size={28} color="var(--mantine-color-dimmed)" />
        </Dropzone.Idle>

        <Stack gap={2} align="center">
          <Text fw={500} size="sm">
            Drop files here or click to browse
          </Text>
          <Text size="xs" c="dimmed">
            Chest X-ray required — .dcm, .png, or .jpg. Max 50 MB per file.
          </Text>
        </Stack>
      </Group>
    </Dropzone>
  )
}
