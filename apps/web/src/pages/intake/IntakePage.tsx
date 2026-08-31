import {
  Alert,
  Box,
  Button,
  Checkbox,
  Divider,
  Group,
  Loader,
  NumberInput,
  Paper,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
} from '@mantine/core'
import { Dropzone, IMAGE_MIME_TYPE } from '@mantine/dropzone'
import { useForm } from '@mantine/form'
import { IconAlertCircle, IconCircleCheck, IconFileUpload } from '@tabler/icons-react'
import { useState } from 'react'

import { Section } from './components'

/**
 * Intake form — data entry with the client sitting opposite.
 *
 * ONE scrolling page, submitted once. NOT a wizard: operators jump around and
 * clients correct themselves, so nothing may be lost between steps.
 *
 * The form is **model-driven** (see docs/INTAKE_FORM.md): the operator picks
 * which model arms apply from a vertical checkbox menu ("click all that
 * applicable"). Each selected model pops out a panel with:
 *   - an instruction telling the operator which report/upload to attach, and
 *   - that model's risk-factor fields.
 *
 * Applicant + coverage stay model-agnostic at the top; evidence is a single
 * dropzone that each model's panel points at.
 *
 * Section completeness is derived from form state:
 *   1 · Applicant   → reference set
 *   2 · Coverage    → type + amount set
 *   3 · Models      → at least one model selected
 *   4 · Evidence    → every selected model's required upload is attached
 *
 * Submit stays disabled until applicant reference + coverage type/amount +
 * ≥1 model selected + all required uploads present.
 *
 * TODO: `POST /api/applications` as `multipart/form-data` in one request,
 * posting `models_requested` + the per-model `declared_history` JSONB shape in
 * DATABASE.md §C; real upload progress; confirmation persists after success.
 */

type Scalar = string | boolean | number | string[] | null

interface ModelValues {
  [key: string]: Scalar
}

type SimpleField =
  | { kind: 'checkbox'; key: string; label: string }
  | { kind: 'select'; key: string; label: string; data: string[]; placeholder?: string }
  | { kind: 'number'; key: string; label: string; description?: string }

interface ModelDef {
  id: string
  label: string
  modality: string
  upload: { category: string; extension: string; instruction: string } | null
  fields: SimpleField[]
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

const SKIN_TYPES = ['I', 'II', 'III', 'IV', 'V', 'VI']

// The model registry drives the whole form. Adding or dropping an arm is one
// entry here (see docs/INTAKE_FORM.md and SPEC.md §6).
const MODELS: ModelDef[] = [
  {
    id: 'cxr_lung',
    label: 'Chest X-ray',
    modality: 'TorchXRayVision (DenseNet)',
    upload: {
      category: 'Chest X-ray',
      extension: '.dcm, .png, .jpg',
      instruction: 'Chest X-ray — .dcm, .png, or .jpg',
    },
    fields: [],
  },
  {
    id: 'mirai',
    label: 'Mirai',
    modality: 'Breast · mammography',
    upload: {
      category: 'Mammogram',
      extension: '.dcm',
      instruction: 'Mammogram, 4 views — .dcm',
    },
    fields: [
      { kind: 'checkbox', key: 'family_breast_cancer', label: 'Family history of breast cancer' },
      { kind: 'checkbox', key: 'prior_biopsy', label: 'Prior breast biopsy' },
      {
        kind: 'select',
        key: 'brca_status',
        label: 'Known BRCA / genetic test result',
        data: ['Not tested', 'Negative', 'Positive'],
        placeholder: 'Not tested',
      },
    ],
  },
  {
    id: 'ham10000',
    label: 'HAM10000',
    modality: 'Dermoscopy · skin',
    upload: {
      category: 'Lesion photo',
      extension: '.png, .jpg',
      instruction: 'Lesion photograph — .png or .jpg',
    },
    fields: [
      { kind: 'select', key: 'skin_type', label: 'Skin type (Fitzpatrick)', data: SKIN_TYPES, placeholder: 'Select' },
      { kind: 'checkbox', key: 'prior_skin_cancer', label: 'Prior skin cancer' },
      {
        kind: 'select',
        key: 'body_site',
        label: 'Body site',
        data: ['Head / neck', 'Upper limb', 'Trunk', 'Lower limb'],
        placeholder: 'Select',
      },
    ],
  },
  {
    id: 'eyepacs',
    label: 'EyePACS',
    modality: 'Retinopathy · fundus',
    upload: {
      category: 'Retinal photo',
      extension: '.png, .jpg, .dcm',
      instruction: 'Retinal / fundus photo — .png, .jpg, or .dcm',
    },
    fields: [
      {
        kind: 'select',
        key: 'diabetes_duration',
        label: 'Diabetes duration',
        data: ['No diabetes', 'Under 5 years', '5–10 years', 'Over 10 years'],
        placeholder: 'Select',
      },
      { kind: 'checkbox', key: 'hypertension', label: 'Hypertension' },
      { kind: 'checkbox', key: 'smoker', label: 'Current or former smoker' },
    ],
  },
  {
    id: 'biobert',
    label: 'BioBERT',
    modality: 'Clinical NLP · EHR',
    upload: {
      category: 'Clinical note',
      extension: '.pdf, .txt',
      instruction: 'Clinical note / physician report — .pdf or .txt',
    },
    fields: [],
  },
  {
    id: 'xgboost',
    label: 'XGBoost',
    modality: 'Actuarial · tabular',
    upload: null,
    fields: [
      { kind: 'number', key: 'height_cm', label: 'Height (cm)', description: 'Feeds the tabular BMI feature.' },
      { kind: 'number', key: 'weight_kg', label: 'Weight (kg)' },
      { kind: 'select', key: 'alcohol', label: 'Alcohol use', data: ['None', 'Occasionally', 'Regularly'], placeholder: 'Select' },
      { kind: 'select', key: 'activity', label: 'Physical activity', data: ['Sedentary', 'Light', 'Moderate', 'Active'], placeholder: 'Select' },
      { kind: 'select', key: 'occupation', label: 'Occupation', data: ['Office / professional', 'Manual / physical', 'Retired', 'Student', 'Not employed'], placeholder: 'Select' },
      { kind: 'checkbox', key: 'smoker', label: 'Current or former smoker' },
    ],
  },
  {
    id: 'neuro',
    label: 'Neuro MRI',
    modality: '3D brain · MONAI',
    upload: {
      category: 'MRI scan',
      extension: '.dcm',
      instruction: 'Brain MRI — .dcm',
    },
    fields: [
      { kind: 'checkbox', key: 'memory_concerns', label: 'Memory concerns' },
      { kind: 'checkbox', key: 'speech_concerns', label: 'Speech concerns' },
      { kind: 'checkbox', key: 'mobility_concerns', label: 'Coordination / mobility concerns' },
    ],
  },
]

const FILE_TYPES: string[] = [
  'Chest X-ray',
  'Mammogram',
  'Retinal photo',
  'Lesion photo',
  'Clinical note',
  'Lab report',
  'MRI scan',
]

const MAX_FILE_BYTES = 50 * 1024 * 1024

interface IntakeForm {
  reference: string
  dob: string
  sex: string | null
  coverageType: string | null
  coverageAmount: number | null
  policyTerm: string | null
  selectedModels: string[]
  modelFields: Record<string, ModelValues>
}

interface EvidenceFile {
  id: string
  name: string
  size: number
  fileType: string
}

function formatSize(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

function bool(v: Scalar | undefined) {
  return v === true
}

export function IntakePage() {
  const form = useForm<IntakeForm>({
    initialValues: {
      reference: '',
      dob: '',
      sex: null,
      coverageType: null,
      coverageAmount: null,
      policyTerm: null,
      selectedModels: [],
      modelFields: {},
    },
  })

  const [files, setFiles] = useState<EvidenceFile[]>([])
  const [rejectNote, setRejectNote] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const toggleSet = (modelId: string, key: string, value: string) => {
    const block = (form.values.modelFields[modelId]?.[key] as string[]) ?? []
    const next = block.includes(value)
      ? block.filter((v) => v !== value)
      : [...block, value]
    setField(modelId, key, next)
  }

  const setField = (modelId: string, key: string, value: Scalar) => {
    form.setFieldValue('modelFields', {
      ...form.values.modelFields,
      [modelId]: { ...(form.values.modelFields[modelId] ?? {}), [key]: value },
    })
  }

  const toggleModel = (id: string) => {
    const has = form.values.selectedModels.includes(id)
    form.setFieldValue(
      'selectedModels',
      has
        ? form.values.selectedModels.filter((m) => m !== id)
        : [...form.values.selectedModels, id],
    )
  }

  const selected = MODELS.filter((m) => form.values.selectedModels.includes(m.id))

  const onDrop = (dropped: File[]) => {
    setRejectNote(null)
    const accepted: EvidenceFile[] = dropped.map((f) => ({
      id: crypto.randomUUID(),
      name: f.name,
      size: f.size,
      fileType: 'Chest X-ray',
    }))
    setFiles((prev) => [...prev, ...accepted])
  }

  const onReject = (rejects: { file: File }[]) => {
    const tooBig = rejects.some((r) => r.file.size > MAX_FILE_BYTES)
    setRejectNote(
      tooBig
        ? 'One or more files were rejected — files over 50 MB are not accepted.'
        : 'One or more files were rejected. Check the accepted types for each model.',
    )
  }

  const removeFile = (id: string) => setFiles((prev) => prev.filter((f) => f.id !== id))

  const hasUploadFor = (model: ModelDef) =>
    model.upload === null ||
    files.some((f) => f.fileType === model.upload!.category)

  const allRequiredUploadsPresent = () =>
    selected.length > 0 && selected.every(hasUploadFor)

  const sections = [
    Boolean(form.values.reference.trim()),
    Boolean(form.values.coverageType) && (form.values.coverageAmount ?? 0) > 0,
    form.values.selectedModels.length > 0,
    allRequiredUploadsPresent(),
  ]
  const completeCount = sections.filter(Boolean).length

  const canSubmit =
    Boolean(form.values.reference.trim()) &&
    Boolean(form.values.coverageType) &&
    (form.values.coverageAmount ?? 0) > 0 &&
    form.values.selectedModels.length > 0 &&
    allRequiredUploadsPresent()

  const handleSubmit = () => {
    if (!canSubmit) return
    setSubmitting(true)
    // TODO: POST /api/applications (multipart) with models_requested +
    // per-model declared_history (DATABASE.md §C), then navigate to the queue.
    window.setTimeout(() => {
      setSubmitting(false)
      setSubmitted(true)
    }, 1200)
  }

  if (submitted) {
    return (
      <Stack gap="md" maw={560}>
        <Alert icon={<IconCircleCheck size={18} />} color="teal" title="Application submitted">
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
    <Stack gap="lg" maw={980}>
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
          Fill this out while the client is in front of you. Pick the models that
          apply, then follow each one’s upload instruction. One page, one submit.
        </Text>
      </div>

      {/* ── Section 1 · Applicant ─────────────────────────────── */}
      <Section n="1" title="Applicant" complete={sections[0]}>
        <TextInput
          label="Reference"
          description="The carrier's own client ID. Must be unique per tenant."
          required
          placeholder="ABC-12345"
          {...form.getInputProps('reference')}
        />
        <Group align="flex-end">
          <TextInput label="Date of birth" type="date" {...form.getInputProps('dob')} />
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
      <Section n="2" title="Coverage requested" complete={sections[1]}>
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
          <Select
            label="Policy term"
            placeholder="Years"
            data={['1', '5', '10', '20']}
            clearable
            {...form.getInputProps('policyTerm')}
          />
        </Group>
      </Section>

      <Divider my="xs" />

      {/* ── Section 3 · Models ─────────────────────────────────── */}
      <Section n="3" title="Models" complete={sections[2]}>
        <Text size="sm" c="dimmed">
          Click all that apply. Each model tells you which report to submit and
          which questions it needs answered.
        </Text>

        <Group align="flex-start" wrap="nowrap" gap="lg">
          {/* Vertical menu */}
          <Stack gap={4} w={260} style={{ flexShrink: 0 }}>
            {MODELS.map((m) => {
              const on = form.values.selectedModels.includes(m.id)
              return (
                <Paper
                  key={m.id}
                  p="xs"
                  bd={on ? '1px solid var(--mantine-color-clinical-6)' : undefined}
                  withBorder={!on}
                  bg={on ? 'var(--mantine-color-clinical-0)' : 'transparent'}
                  style={{ cursor: 'pointer' }}
                  onClick={() => toggleModel(m.id)}
                >
                  <Checkbox
                    label={m.label}
                    description={m.modality}
                    checked={on}
                    readOnly
                    styles={{ label: { fontWeight: 600 } }}
                  />
                </Paper>
              )
            })}
          </Stack>

          {/* Pop-out panels for selected models */}
          <Stack gap="md" style={{ flex: 1, minWidth: 0 }}>
            {selected.length === 0 && (
              <Text size="sm" c="dimmed">
                Nothing selected yet — pick at least one model from the menu.
              </Text>
            )}
            {selected.map((m) => (
              <Paper key={m.id} bd="1px solid var(--mantine-color-default-border)" p="md">
                <Group justify="space-between" mb="sm">
                  <Text fw={600} size="sm">
                    {m.label}
                    <Text span c="dimmed" fw={400}>
                      {' '}
                      · {m.modality}
                    </Text>
                  </Text>
                </Group>

                {m.upload ? (
                  <Alert
                    icon={<IconFileUpload size={16} />}
                    color="clinical"
                    variant="light"
                    mb="md"
                  >
                    <Text size="sm">
                      Please submit: <Text span fw={600}>{m.upload.instruction}</Text>
                    </Text>
                  </Alert>
                ) : (
                  <Alert color="gray" variant="light" mb="md">
                    <Text size="sm">No report needed — complete the demographic form.</Text>
                  </Alert>
                )}

                <ModelFieldControls
                  model={m}
                  values={form.values.modelFields[m.id] ?? {}}
                  setField={setField}
                  toggleSet={toggleSet}
                />
              </Paper>
            ))}
          </Stack>
        </Group>
      </Section>

      <Divider my="xs" />

      {/* ── Section 4 · Evidence ───────────────────────────────── */}
      <Section n="4" title="Evidence" complete={sections[3]}>
        <Text size="sm" c="dimmed" mb="xs">
          Attach the reports each selected model asked for. Upload progress below.
        </Text>
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
          In Phase 1 only the chest X-ray is analysed. Other reports (mammograms,
          retinal photos, lesions, MRIs, clinical notes) are stored for the arms
          that read them.
        </Text>
      </Section>

      <Divider my="xs" />

      <Group justify="space-between" align="flex-start">
        <Text size="xs" c="dimmed" maw={420}>
          Disabled until reference, coverage type and amount are filled, at least
          one model is selected, and every required report is attached.
        </Text>
        <Button size="sm" disabled={!canSubmit} loading={submitting} onClick={handleSubmit}>
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

function ModelFieldControls({
  model,
  values,
  setField,
  toggleSet,
}: {
  model: ModelDef
  values: ModelValues
  setField: (modelId: string, key: string, value: Scalar) => void
  toggleSet: (modelId: string, key: string, value: string) => void
}) {
  if (model.id === 'cxr_lung') {
    return (
      <CxrPanel values={values} setField={setField} toggleSet={toggleSet} />
    )
  }

  if (model.fields.length === 0) {
    return (
      <Text size="xs" c="dimmed">
        No additional questions — the {model.label} model reads the uploaded report directly.
      </Text>
    )
  }

  return (
    <Stack gap="sm">
      {model.fields.map((f) => {
        if (f.kind === 'checkbox') {
          return (
            <Checkbox
              key={f.key}
              label={f.label}
              checked={bool(values[f.key])}
              onChange={(e) => setField(model.id, f.key, e.currentTarget.checked)}
            />
          )
        }
        if (f.kind === 'select') {
          return (
            <Select
              key={f.key}
              label={f.label}
              placeholder={f.placeholder ?? 'Select'}
              data={f.data}
              clearable
              value={typeof values[f.key] === 'string' ? (values[f.key] as string) : null}
              onChange={(v) => setField(model.id, f.key, v)}
            />
          )
        }
        return (
          <NumberInput
            key={f.key}
            label={f.label}
            description={f.description}
            min={0}
            value={typeof values[f.key] === 'number' ? (values[f.key] as number) : undefined}
            onChange={(v) => setField(model.id, f.key, v === '' ? null : v)}
          />
        )
      })}
    </Stack>
  )
}

function CxrPanel({
  values,
  setField,
  toggleSet,
}: {
  values: ModelValues
  setField: (modelId: string, key: string, value: Scalar) => void
  toggleSet: (modelId: string, key: string, value: string) => void
}) {
  const modelId = 'cxr_lung'
  const sym = (values.symptoms as string[]) ?? []
  const hist = (values.history as string[]) ?? []
  const cardio = (values.cardio as string[]) ?? []

  return (
    <Stack gap="md">
      {/* Current symptoms */}
      <Box>
        <Text fw={600} size="sm" mb="xs">
          Current symptoms
        </Text>
        <Stack gap="xs">
          {SYMPTOMS.map((s) => (
            <Checkbox
              key={s}
              label={s}
              checked={sym.includes(s)}
              onChange={() => toggleSet(modelId, 'symptoms', s)}
            />
          ))}
        </Stack>
      </Box>

      {/* TB history */}
      <Box>
        <Text fw={600} size="sm" mb="xs">
          Medical history
        </Text>
        <Stack gap="xs">
          <Checkbox
            label="Previously treated for TB"
            checked={bool(values.prior_tb)}
            onChange={(e) => setField(modelId, 'prior_tb', e.currentTarget.checked)}
          />
          {bool(values.prior_tb) && (
            <Box pl="lg">
              <Checkbox
                label="Completed the full course of treatment"
                checked={bool(values.prior_tb_treatment_completed)}
                onChange={(e) =>
                  setField(modelId, 'prior_tb_treatment_completed', e.currentTarget.checked)
                }
              />
            </Box>
          )}
          {HISTORY_ONCE.map((h) => (
            <Checkbox
              key={h}
              label={h}
              checked={hist.includes(h)}
              onChange={() => toggleSet(modelId, 'history', h)}
            />
          ))}
        </Stack>
      </Box>

      {/* Cardio */}
      <Box>
        <Text fw={600} size="sm" mb="xs">
          Cardiovascular
        </Text>
        <Stack gap="xs">
          {['Hypertension', 'High cholesterol', 'Family history of heart disease'].map((c) => (
            <Checkbox
              key={c}
              label={c}
              checked={cardio.includes(c)}
              onChange={() => toggleSet(modelId, 'cardio', c)}
            />
          ))}
        </Stack>
      </Box>
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
            Max 50 MB per file.
          </Text>
        </Stack>
      </Group>
    </Dropzone>
  )
}
