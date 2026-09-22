import {
  Alert,
  Anchor,
  FileButton,
  Badge,
  Box,
  Button,
  Divider,
  Group,
  Image,
  NumberInput,
  Paper,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  Tooltip,
  Textarea,
  TextInput,
  Modal,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import {
  IconAlertTriangle,
  IconChevronDown,
  IconCircleCheck,
  IconShieldCheck,
  IconShieldX,
} from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  escalateApplication,
  fileUrl,
  fulfilEvidenceRequest,
  getApplication,
  getAuditTrail,
  recordDecision,
  requestEvidence,
  reviseTurnaround,
  type ApplicationDetail,
  type ArmRun,
  type EvidenceFile,
  type DecisionType,
  type Finding,
  type Plan,
} from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { StatusBadge } from '../../components/StatusBadge'
import { ScoringProgress } from './ScoringProgress'
import { ErrorState, LoadingState } from '../../components/states'
import { TierBadge, type Tier } from '../../components/TierBadge'
import { useAuth } from '../../context/AuthContext'
import { ROLE_LABEL } from '../../types/auth'

/**
 * Review workspace — the underwriter, alone, a day or two later.
 *
 * Answers one question: should I trust this recommendation, and what do I
 * decide? Evidence on the left, reasoning and decision on the right.
 *
 * Decision invariants:
 *  · NO reject button — escalation is the path.
 *  · Decisions are write-once; the panel becomes read-only once one exists.
 *  · `approved_with_adjustment` reveals a final-premium input.
 */

const DECISIONS: { value: DecisionType; label: string }[] = [
  { value: 'confirmed_fast_track', label: 'Confirm fast-track' },
  { value: 'approved_with_adjustment', label: 'Approve with adjustment' },
  { value: 'escalated_senior_review', label: 'Escalate to a medical professional' },
  // "Request more evidence" is deliberately not here. Decisions are
  // write-once, so recording a request as one would decide the application
  // forever the moment a document was asked for. It has its own panel and
  // its own endpoint, and the decision stays open while the applicant is
  // being waited on.
]

const TOP_N = 5

/** "Tue 29 Sep" — parsed as local midnight so a bare date never shifts a day. */
function formatDay(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
}

/** `Pleural_Thickening` is the model's own spelling; show it readably. */
const prettyLabel = (label: string) => label.replace(/_/g, ' ')

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

function FindingBar({ finding, scale }: { finding: Finding; scale: number }) {
  const toward = finding.contribution >= 0
  const width = scale > 0 ? (Math.abs(finding.contribution) / scale) * 100 : 0

  return (
    <div>
      <Group justify="space-between" mb={4} wrap="nowrap">
        <Text size="xs">{prettyLabel(finding.label)}</Text>
        <Group gap="xs" wrap="nowrap">
          <Text size="xs" ff="monospace" c="dimmed">
            p={finding.probability.toFixed(2)}
          </Text>
          <Text size="xs" ff="monospace" c={toward ? 'clinical.4' : 'dimmed'}>
            {finding.contribution >= 0 ? '+' : ''}
            {finding.contribution.toFixed(2)}
          </Text>
        </Group>
      </Group>
      <Box
        h={6}
        w="100%"
        style={{ backgroundColor: 'var(--neo-hover)', borderRadius: 3 }}
      >
        <Box
          h="100%"
          className="finding-bar__fill"
          style={{
            width: `${Math.min(width, 100)}%`,
            backgroundColor: toward ? 'var(--neo-accent)' : 'var(--neo-muted)',
            borderRadius: 3,
          }}
        />
      </Box>
    </div>
  )
}

export function ReviewPage() {
  const { id = '' } = useParams()
  const queryClient = useQueryClient()

  const [showHeatmap, setShowHeatmap] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [decision, setDecision] = useState<DecisionType | null>(null)
  const [premium, setPremium] = useState<number | undefined>(undefined)

  // Asking the applicant for documents. One item per line, in the
  // underwriter's own words, because the applicant sees them verbatim.
  const [requestOpen, setRequestOpen] = useState(false)
  const [requestItems, setRequestItems] = useState('')
  const [requestNote, setRequestNote] = useState('')

  // Moving the date the applicant was given. A reason is required and shown
  // to them: a date that moves silently is the slip this feature replaces.
  const [reviseOpen, setReviseOpen] = useState(false)
  const [reviseDate, setReviseDate] = useState('')
  const [reviseReason, setReviseReason] = useState('')

  const { data, isPending, error } = useQuery({
    queryKey: ['application', id],
    queryFn: () => getApplication(id),
    enabled: Boolean(id),
    // An application still being scored settles within seconds.
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'submitted' || status === 'processing' ? 3_000 : false
    },
  })

  // Escalating is a hand-over, not a decision, and has its own endpoint. The
  // buttons sit together because that is where the person looks for it.
  const [escalateNote, setEscalateNote] = useState('')

  const submit = useMutation({
    // The two calls return different shapes; the screen refetches anyway.
    mutationFn: async (): Promise<void> => {
      if (decision === 'escalated_senior_review') {
        await escalateApplication(id, { note: escalateNote.trim() || null })
      } else {
        await recordDecision(id, {
          decision: decision as DecisionType,
          finalPremium: decision === 'approved_with_adjustment' ? premium : null,
        })
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['application', id] })
      void queryClient.invalidateQueries({ queryKey: ['applications'] })
      void queryClient.invalidateQueries({ queryKey: ['audit', id] })
      if (decision === 'escalated_senior_review') {
        notifications.show({
          title: 'Handed to a medical professional',
          message: 'They have been told. The decision is now theirs.',
          color: 'grape',
        })
      } else {
        notifications.show({ title: 'Decision recorded', message: 'It cannot be changed.', color: 'teal' })
      }
    },
    onError: (err) => {
      notifications.show({
        title: 'Could not record the decision',
        message: err instanceof Error ? err.message : 'Unknown error',
        color: 'red',
      })
    },
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['application', id] })
    void queryClient.invalidateQueries({ queryKey: ['applications'] })
    void queryClient.invalidateQueries({ queryKey: ['audit', id] })
  }

  const request = useMutation({
    mutationFn: () =>
      requestEvidence(id, {
        items: requestItems.split('\n').map((line) => line.trim()).filter(Boolean),
        note: requestNote.trim() || null,
      }),
    onSuccess: (items) => {
      setRequestOpen(false)
      setRequestItems('')
      setRequestNote('')
      invalidate()
      notifications.show({
        title: 'Request sent',
        message: `${items.length} document${items.length === 1 ? '' : 's'} requested. The application is now waiting on the applicant.`,
        color: 'orange',
      })
    },
    onError: (err) => {
      notifications.show({
        title: 'Could not send the request',
        message: err instanceof Error ? err.message : 'Unknown error',
        color: 'red',
      })
    },
  })

  const revise = useMutation({
    mutationFn: () => reviseTurnaround(id, { expectedBy: reviseDate, reason: reviseReason.trim() }),
    onSuccess: () => {
      setReviseOpen(false)
      setReviseDate('')
      setReviseReason('')
      invalidate()
      notifications.show({
        title: 'Expected date updated',
        message: 'The applicant will see the new date and the reason.',
        color: 'teal',
      })
    },
    onError: (err) => {
      notifications.show({
        title: 'Could not update the date',
        message: err instanceof Error ? err.message : 'Unknown error',
        color: 'red',
      })
    },
  })

  const receive = useMutation({
    mutationFn: ({ documentId, file }: { documentId: string; file?: File | null }) =>
      fulfilEvidenceRequest(id, documentId, file),
    onSuccess: invalidate,
    onError: (err) => {
      notifications.show({
        title: 'Could not mark it received',
        message: err instanceof Error ? err.message : 'Unknown error',
        color: 'red',
      })
    },
  })

  if (isPending) {
    return (
      <Stack gap="md">
        <PageHeader screen="review" title="Opening the application" />
        <LoadingState label="Loading the evidence and the score" />
      </Stack>
    )
  }

  if (error || !data) {
    return (
      <Stack gap="md">
        <PageHeader screen="review" title="Application" />
        <ErrorState
          title="Could not open this application"
          error={error}
          retry={() => void queryClient.invalidateQueries({ queryKey: ['application', id] })}
        />
      </Stack>
    )
  }

  return (
    <Review
      data={data}
      state={{
        showHeatmap,
        setShowHeatmap,
        showAll,
        setShowAll,
        decision,
        setDecision,
        premium,
        setPremium,
        escalateNote,
        setEscalateNote,
        submit,
        requestOpen,
        setRequestOpen,
        requestItems,
        setRequestItems,
        requestNote,
        setRequestNote,
        request,
        receive,
        reviseOpen,
        setReviseOpen,
        reviseDate,
        setReviseDate,
        reviseReason,
        setReviseReason,
        revise,
      }}
    />
  )
}

interface ReviewState {
  showHeatmap: boolean
  setShowHeatmap: (v: boolean) => void
  showAll: boolean
  setShowAll: (v: boolean) => void
  decision: DecisionType | null
  setDecision: (v: DecisionType) => void
  premium: number | undefined
  setPremium: (v: number | undefined) => void
  escalateNote: string
  setEscalateNote: (v: string) => void
  submit: { mutate: () => void; isPending: boolean }
  requestOpen: boolean
  setRequestOpen: (v: boolean) => void
  requestItems: string
  setRequestItems: (v: string) => void
  requestNote: string
  setRequestNote: (v: string) => void
  request: { mutate: () => void; isPending: boolean }
  receive: { mutate: (v: { documentId: string; file?: File | null }) => void; isPending: boolean }
  reviseOpen: boolean
  setReviseOpen: (v: boolean) => void
  reviseDate: string
  setReviseDate: (v: string) => void
  reviseReason: string
  setReviseReason: (v: string) => void
  revise: { mutate: () => void; isPending: boolean }
}

/** Derive a human-readable image label from whichever arm produced the evidence. */
// Whole years between the date of birth and the submission, as the API counted them.
function ageAt(dateOfBirth: string | null | undefined, when: string | null | undefined): number | null {
  if (!dateOfBirth) return null
  const born = new Date(dateOfBirth)
  const at = when ? new Date(when) : new Date()
  let years = at.getFullYear() - born.getFullYear()
  const beforeBirthday =
    at.getMonth() < born.getMonth() ||
    (at.getMonth() === born.getMonth() && at.getDate() < born.getDate())
  if (beforeBirthday) years -= 1
  return years >= 0 ? years : null
}

/**
 * One evidence image, with its own heatmap overlay.
 *
 * The label comes from the file's own `evidenceLabel` — what the platform
 * identified it as and the operator confirmed. It used to be guessed from the
 * requested-model list, which labelled a chest film "12-lead ECG" whenever
 * both were attached, and showed only the first image however many arrived.
 */
function EvidencePanel({ file, heatmap }: { file: EvidenceFile; heatmap?: EvidenceFile }) {
  const [overlay, setOverlay] = useState(false)
  const label = file.evidenceLabel ?? 'Evidence'
  const isTracing = file.evidenceKind === 'ecg'

  return (
    <Paper p="sm" bd="1px solid var(--mantine-color-default-border)">
      <Group justify="space-between" mb="sm" wrap="nowrap">
        <div style={{ minWidth: 0 }}>
          <Text fw={600} size="sm">
            {label}
          </Text>
          <Text size="xs" truncate style={{ color: 'var(--neo-muted)' }}>
            {file.filename}
            {file.uploadedAt ? ` · uploaded ${relativeTime(file.uploadedAt)}` : ''}
          </Text>
        </div>
        <Switch
          label="Heatmap overlay"
          size="xs"
          checked={overlay && Boolean(heatmap)}
          onChange={() => setOverlay(!overlay)}
          disabled={!heatmap}
        />
      </Group>

      <Box
        h={340}
        style={{
          display: 'grid',
          placeItems: 'center',
          backgroundColor: 'var(--neo-bg)',
          borderRadius: 'var(--mantine-radius-sm)',
          overflow: 'hidden',
        }}
      >
        <Image
          src={fileUrl(overlay && heatmap ? heatmap.id : file.id)}
          alt={overlay ? `${label} with model heatmap` : label}
          h={340}
          fit="contain"
        />
      </Box>
      <Text size="xs" c="dimmed" mt="sm">
        {heatmap
          ? isTracing
            ? 'The shading marks where in the tracing the network looked for the reported abnormality — not a diagnosis.'
            : 'The overlay marks the region that moved the score most — not a diagnosis.'
          : 'No heatmap was produced for this image.'}
      </Text>
    </Paper>
  )
}

function Review({ data, state }: { data: ApplicationDetail; state: ReviewState }) {
  const findings = data.findings ?? []
  const adjustments = data.adjustments ?? []
  const files = data.files ?? []
  const errors = data.errors ?? []

  // A note is stored as text and read in its own panel; the image box is for
  // the evidence that is a picture (or, for an ECG, drawn as one).
  const isText = (f: { mimeType?: string | null }) => Boolean(f.mimeType?.startsWith('text/'))
  const images = files.filter((f) => f.kind === 'evidence' && !isText(f))
  const evidence = images[0]
  const note = files.find((f) => f.kind === 'evidence' && isText(f))
  const heatmaps = files.filter((f) => f.kind === 'gradcam')
  // Each overlay goes over the image its reader read (`ofFileId`). Older
  // applications, scored before the API said which, fall back to the first.
  const heatmapFor = (image: EvidenceFile) =>
    heatmaps.find((h) => h.ofFileId === image.id) ??
    (heatmaps.length === 1 && images.length === 1 ? heatmaps[0] : undefined)

  // Each arm's own report. The image and findings panels above belong to the
  // vision arm; an application scored from the blood panel alone has neither,
  // and showing "no image was stored" for it would read as a fault.
  const arms = data.arms ?? []
  const hasVision = arms.some((a) => a.armType === 'vision') || Boolean(evidence)

  // Ranked by absolute contribution: the findings that moved the score most, in
  // either direction. Not by probability — the two disagree, and contribution
  // is the one that explains the number.
  const ranked = [...findings].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  )
  const shown = state.showAll ? ranked : ranked.slice(0, TOP_N)
  const scale = Math.max(...ranked.map((f) => Math.abs(f.contribution)), 0.01)

  const decided = Boolean(data.decision)
  const scored =
    data.status === 'scored' || data.status === 'decided' || data.status === 'escalated'
  const escalated = data.status === 'escalated'
  const pending = data.status === 'submitted' || data.status === 'processing'

  const { user } = useAuth()
  const isElevated = data.score?.tier === 'elevated'
  const isUnderwriter = user?.role === 'underwriter'
  const isMedical = user?.role === 'medical_professional'

  return (
    <Stack gap="md">
      <PageHeader
        screen="review"
        title={
          <span>
            Application <span className="hl-mono">{data.reference}</span>
          </span>
        }
      />

      {/* ── Header ─────────────────────────────────────────── */}
      <Paper p="sm" bd="1px solid var(--mantine-color-default-border)">
        <Group justify="space-between" wrap="wrap" gap="md">
          <Group gap="md">
            <div className="hl-kv">
              <span className="hl-kv-label">Reference</span>
              <span className="hl-kv-value hl-mono">{data.reference}</span>
            </div>
            <Divider orientation="vertical" />
            <div className="hl-kv">
              <span className="hl-kv-label">Status</span>
              <StatusBadge status={data.status} />
            </div>
            <Divider orientation="vertical" />
            <div className="hl-kv">
              <span className="hl-kv-label">Client</span>
              <span className="hl-kv-value">{data.applicant.name || '—'}</span>
            </div>
            <div className="hl-kv">
              <span className="hl-kv-label">Submitted</span>
              <span className="hl-kv-value">{relativeTime(data.submittedAt)}</span>
            </div>
            {/* A date, never a countdown. Red once it has passed while the
                carrier still holds the case; not while waiting on the
                applicant, whose delay it would be. */}
            <div className="hl-kv">
              <span className="hl-kv-label">Expected by</span>
              <Group gap={6} wrap="nowrap" align="center">
                <span className="hl-kv-value" style={{ color: data.overdue ? 'var(--mantine-color-red-5)' : undefined }}>
                  {data.expectedBy ? formatDay(data.expectedBy) : 'Not set'}
                </span>
                {data.overdue && (
                  <Badge size="xs" color="red" variant="light">
                    Late
                  </Badge>
                )}
                {!decided && (
                  <Button
                    size="compact-xs"
                    variant="subtle"
                    onClick={() => {
                      state.setReviseDate(data.expectedBy ?? '')
                      state.setReviseOpen(true)
                    }}
                  >
                    Revise
                  </Button>
                )}
              </Group>
              {data.expectedByNote && (
                <Text size="xs" c="dimmed">
                  {data.expectedByNote}
                </Text>
              )}
            </div>

            <Modal
              opened={state.reviseOpen}
              onClose={() => state.setReviseOpen(false)}
              title="Revise the expected date"
              size="sm"
            >
              <Stack gap="sm">
                <Text size="sm" c="dimmed">
                  The applicant sees the new date and your reason. Weekends do not
                  count as working days.
                </Text>
                <TextInput
                  size="xs"
                  type="date"
                  label="Expected by"
                  value={state.reviseDate}
                  onChange={(e) => state.setReviseDate(e.currentTarget.value)}
                />
                <Textarea
                  size="xs"
                  label="Reason"
                  placeholder="Waiting on the radiology report from the applicant's hospital."
                  autosize
                  minRows={2}
                  value={state.reviseReason}
                  onChange={(e) => state.setReviseReason(e.currentTarget.value)}
                />
                <Group justify="flex-end" gap="xs">
                  <Button size="xs" variant="subtle" onClick={() => state.setReviseOpen(false)}>
                    Cancel
                  </Button>
                  <Button
                    size="xs"
                    onClick={() => state.revise.mutate()}
                    loading={state.revise.isPending}
                    disabled={!state.reviseDate || state.reviseReason.trim().length < 3}
                  >
                    Save new date
                  </Button>
                </Group>
              </Stack>
            </Modal>
          </Group>
          {data.score && (
            <Group gap="sm">
              <div className="hl-kv score-reveal" style={{ alignItems: 'flex-end' }}>
                <span className="hl-kv-label">Risk score</span>
                <span className="hl-kv-value" style={{ fontSize: '1.1rem' }}>
                  {data.score.crs.toFixed(1)}
                </span>
              </div>
              <TierBadge tier={data.score.tier as Tier} />
            </Group>
          )}
        </Group>
      </Paper>

      {pending && <ScoringProgress status={data.status} />}

      {data.status === 'insufficient_evidence' && (
        <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={18} />} title="Could not be scored">
          <Stack gap={4}>
            <Text size="sm">
              There was not enough usable evidence to produce a score. Nothing here is a
              judgement about the applicant — request more evidence to continue.
            </Text>
            {errors.map((message) => (
              <Text key={message} size="xs" c="dimmed" ff="monospace">
                {message}
              </Text>
            ))}
          </Stack>
        </Alert>
      )}

      {hasVision && (
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        {/* ── Left · the evidence, one panel per image ─────── */}
        <Stack gap="md">
          {images.length > 0 ? (
            images.map((image) => (
              <EvidencePanel key={image.id} file={image} heatmap={heatmapFor(image)} />
            ))
          ) : (
            <Paper p="sm" bd="1px solid var(--mantine-color-default-border)">
              <Text c="dimmed" size="sm">
                No image was stored for this application.
              </Text>
            </Paper>
          )}
        </Stack>

        {/* ── Right · why this score ────────────────────────── */}
        <Stack gap="md">
          <Paper p="sm" bd="1px solid var(--mantine-color-default-border)">
            <Group justify="space-between" mb={4}>
              <Text fw={600} size="sm">
                What moved the score
              </Text>
              <Text size="xs" c="dimmed">
                {shown.length} of {findings.length} shown
              </Text>
            </Group>
            <Text size="xs" mb="sm" style={{ color: 'var(--neo-muted)' }}>
              Findings from the image, ranked by how much each moved the score. The first
              figure is how confident the model is that the finding is present; the second is
              its push on the score, up or down.
            </Text>

            {findings.length === 0 ? (
              <Text size="sm" c="dimmed">
                The model produced no findings for this application.
              </Text>
            ) : (
              <>
                <Stack gap="sm">
                  {shown.map((f) => (
                    <FindingBar key={f.label} finding={f} scale={scale} />
                  ))}
                </Stack>
                <Button
                  variant="subtle"
                  size="xs"
                  mt="sm"
                  fullWidth
                  rightSection={<IconChevronDown size={14} />}
                  onClick={() => state.setShowAll(!state.showAll)}
                >
                  {state.showAll ? `Show top ${TOP_N}` : `Show all ${findings.length}`}
                </Button>
              </>
            )}
          </Paper>

          <Paper p="sm" bd="1px solid var(--mantine-color-default-border)">
            <Text fw={600} size="sm" mb={4}>
              What the declared history changed
            </Text>
            <Text size="xs" mb="sm" style={{ color: 'var(--neo-muted)' }}>
              Points added or removed by the answers given at intake, applied after the image score.
            </Text>
            {adjustments.length === 0 ? (
              <Text size="sm" c="dimmed">
                Nothing declared changed the score. It is the imaging result alone.
              </Text>
            ) : (
              <Stack gap={6}>
                {adjustments.map((a) => (
                  <Group key={a.key} gap="sm" wrap="nowrap" align="flex-start">
                    <Badge
                      size="sm"
                      variant="light"
                      color={a.points >= 0 ? 'orange' : 'teal'}
                      ff="monospace"
                    >
                      {a.points >= 0 ? '+' : ''}
                      {a.points}
                    </Badge>
                    <Text size="sm" c="dimmed" style={{ flex: 1 }}>
                      {a.reason}
                    </Text>
                  </Group>
                ))}
              </Stack>
            )}
          </Paper>

          {/*
            The validation string is not decoration: the model has only ever
            been tested on one hospital, and that caveat has to travel with the
            score rather than live in a document.
          */}
          {data.modelInfo && (
            <Stack gap={2}>
              <Text size="xs" c="dimmed">
                {data.modelInfo.scorer} · evaluated {relativeTime(data.evaluatedAt)}
              </Text>
              {data.modelInfo.validation && (
                <Text size="xs" c="yellow.7">
                  {data.modelInfo.validation}
                  {data.modelInfo.cvAuc != null && ` (AUC ${data.modelInfo.cvAuc.toFixed(3)})`}
                </Text>
              )}
            </Stack>
          )}
        </Stack>
      </SimpleGrid>
      )}

      {/* ── The tracing: what was reported, and the ECG age ──── */}
      {/* Every reader that ran, in the order it ran. One panel per run, not
          per reader name: two retinal photos are two readings and both belong
          on the screen. A reader with no panel of its own falls back to a
          plain one, so a reading is never dropped because nobody wrote a
          view for it. */}
      {arms.map((run, i) => {
        const key = `${run.arm}-${i}`
        if (run.arm === 'ecg_12lead') {
          return (
            <EcgPanel key={key} run={run} age={ageAt(data.applicant.dateOfBirth, data.submittedAt)} />
          )
        }
        if (run.arm === 'mirai') return <MiraiPanel key={key} run={run} />
        if (run.arm === 'medication_check') {
          return <MedicationPanel key={key} run={run} noteId={note?.id ?? null} />
        }
        if (run.arm === 'mortality') return <MortalityPanel key={key} run={run} />
        return <ReaderPanel key={key} run={run} />
      })}

      {/* ── What this means for the policy ──────────────────── */}
      {data.plan && <PlanPanel plan={data.plan} coverage={data.coverage} />}

      {/* ── Requested documents ─────────────────────────────── */}
      {((data.requestedDocuments ?? []).length > 0 || (!decided && !pending)) && (
        <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
          <Group justify="space-between" align="center" mb="sm">
            <Text fw={600} size="sm">
              Documents requested from the applicant
            </Text>
            {data.status === 'awaiting_evidence' && (
              <Badge color="orange" variant="light" size="xs">
                Waiting on applicant
              </Badge>
            )}
          </Group>

          {(data.requestedDocuments ?? []).length === 0 && (
            <Text size="sm" c="dimmed" mb="sm">
              Nothing has been requested.
            </Text>
          )}

          <Stack gap={6} mb="sm">
            {(data.requestedDocuments ?? []).map((doc) => (
              <Group key={doc.id} justify="space-between" wrap="nowrap">
                <Text
                  size="sm"
                  c={doc.fulfilledAt ? 'dimmed' : undefined}
                  td={doc.fulfilledAt ? 'line-through' : undefined}
                >
                  {doc.description}
                </Text>
                {doc.fulfilledAt ? (
                  <Group gap={6} wrap="nowrap">
                    <Badge size="xs" variant="light" color="teal">
                      Received
                    </Badge>
                    {doc.fulfilledByFileId && (
                      <Anchor href={fileUrl(doc.fulfilledByFileId)} target="_blank" size="xs">
                        Open the document
                      </Anchor>
                    )}
                  </Group>
                ) : (
                  <Group gap={6} wrap="nowrap">
                    <FileButton
                      onChange={(file) => file && state.receive.mutate({ documentId: doc.id, file })}
                      accept="image/png,image/jpeg,application/pdf,text/plain,text/csv,application/dicom"
                    >
                      {(props) => (
                        <Button {...props} size="xs" variant="light" loading={state.receive.isPending}>
                          Attach and mark received
                        </Button>
                      )}
                    </FileButton>
                    <Button
                      size="xs"
                      variant="subtle"
                      onClick={() => state.receive.mutate({ documentId: doc.id })}
                      loading={state.receive.isPending}
                    >
                      Received, no file
                    </Button>
                  </Group>
                )}
              </Group>
            ))}
          </Stack>

          {!decided &&
            (state.requestOpen ? (
              <Stack gap="xs">
                <Textarea
                  size="xs"
                  label="What is needed"
                  description="One document per line, in words the applicant will understand."
                  placeholder={'A chest X-ray taken within the last 6 months\nHbA1c blood test result'}
                  autosize
                  minRows={2}
                  value={state.requestItems}
                  onChange={(e) => state.setRequestItems(e.currentTarget.value)}
                />
                <Textarea
                  size="xs"
                  label="Note to the applicant (optional)"
                  autosize
                  minRows={1}
                  value={state.requestNote}
                  onChange={(e) => state.setRequestNote(e.currentTarget.value)}
                />
                <Group justify="flex-end" gap="xs">
                  <Button size="xs" variant="subtle" onClick={() => state.setRequestOpen(false)}>
                    Cancel
                  </Button>
                  <Button
                    size="xs"
                    color="orange"
                    onClick={() => state.request.mutate()}
                    loading={state.request.isPending}
                    disabled={state.requestItems.split('\n').every((line) => !line.trim())}
                  >
                    Send request
                  </Button>
                </Group>
              </Stack>
            ) : (
              <Button
                size="xs"
                variant="light"
                color="orange"
                onClick={() => state.setRequestOpen(true)}
              >
                Request more evidence
              </Button>
            ))}

          <Text size="xs" c="dimmed" mt="sm">
            Asking for documents pauses the application. It does not decide it; the
            decision below stays open.
          </Text>
        </Paper>
      )}

      {/* ── Decision ────────────────────────────────────────── */}
      <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
        <Group justify="space-between" align="center" mb="sm">
          <Text fw={600} size="sm">
            Decision
          </Text>
          {user && (
            <Text size="xs" style={{ color: 'var(--neo-muted)' }}>
              Deciding as {ROLE_LABEL[user.role]}
            </Text>
          )}
        </Group>
        {!decided && (
          <Text size="xs" mb="sm" style={{ color: 'var(--neo-muted)' }}>
            Pick one. It is recorded under your name, written to the audit trail, and cannot be
            changed afterwards. The client is emailed that there is an update.
          </Text>
        )}

        {isMedical && isElevated && !decided && !escalated && (
          <Alert color="grape" variant="light" icon={<IconShieldCheck size={18} />} title="Elevated risk" mb="sm">
            <Text size="xs">
              The models put this application in the elevated tier. Only a medical professional can
              approve it, and that is you. Read the image and the findings, then decide.
            </Text>
          </Alert>
        )}

        {escalated && !decided && (
          <Alert color="grape" variant="light" icon={<IconShieldCheck size={18} />} title="With a medical professional" mb="sm">
            <Text size="xs">
              {isMedical
                ? 'An underwriter passed this application to you. The decision is yours to record.'
                : 'This application has been passed to a medical professional. Only they can decide it now.'}
            </Text>
          </Alert>
        )}

        {isUnderwriter && isElevated && !decided && !escalated && (
          <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} />} title="Elevated risk" mb="sm">
            <Text size="xs">
              The models put this application in the elevated tier. You can escalate it to a
              medical professional; approving it is not available to you.
            </Text>
          </Alert>
        )}

        {decided ? (
          <Alert
            icon={<IconCircleCheck size={18} />}
            color="teal"
            variant="light"
            title="Decision recorded"
            className="decision-recorded"
          >
            <Text size="sm">
              <strong>
                {DECISIONS.find((d) => d.value === data.decision?.decision)?.label ??
                  data.decision?.decision}
              </strong>{' '}
              by {data.decision?.underwriterName ?? 'an underwriter'},{' '}
              {relativeTime(data.decision?.decidedAt)}.
              {data.decision?.finalPremium != null &&
                ` Final premium ${Number(data.decision.finalPremium).toLocaleString()}.`}{' '}
              A recorded decision cannot be changed.
            </Text>
          </Alert>
        ) : !scored && data.status !== 'insufficient_evidence' && data.status !== 'awaiting_evidence' ? (
          <Text size="sm" c="dimmed">
            A decision can be recorded once the models have finished reading the evidence.
          </Text>
        ) : (
          <>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
              {DECISIONS.filter((d) => !(escalated && d.value === 'escalated_senior_review')).map((d) => {
                const isApprovalAction =
                  d.value === 'confirmed_fast_track' || d.value === 'approved_with_adjustment'
                const isBlockedForUnderwriter =
                  isUnderwriter && isApprovalAction && (isElevated || escalated)
                const isEscalate = d.value === 'escalated_senior_review'

                const btn = (
                  <Button
                    key={d.value}
                    variant={state.decision === d.value ? 'filled' : 'light'}
                    color={
                      state.decision === d.value
                        ? isEscalate
                          ? 'orange'
                          : isMedical
                          ? 'grape'
                          : 'clinical'
                        : 'gray'
                    }
                    justify="space-between"
                    disabled={isBlockedForUnderwriter}
                    onClick={() => {
                      state.setDecision(d.value)
                      // Start from the plan's figure rather than an empty box, so
                      // the rate is anchored to the tier and the cover requested.
                      // The underwriter still sets the final number.
                      if (d.value === 'approved_with_adjustment' && state.premium == null) {
                        state.setPremium(data.plan?.monthlyPremiumBdt ?? undefined)
                      }
                    }}
                  >
                    {d.label}
                  </Button>
                )

                if (isBlockedForUnderwriter) {
                  return (
                    <Tooltip
                      key={d.value}
                      label={
                        escalated
                          ? 'Escalated: a medical professional decides this'
                          : 'Elevated risk: escalate this to a medical professional'
                      }
                      withArrow
                    >
                      <div>{btn}</div>
                    </Tooltip>
                  )
                }

                return btn
              })}
            </SimpleGrid>

            {state.decision === 'escalated_senior_review' && (
              <Textarea
                mt="md"
                label="A note for the medical professional"
                description="Optional. What you want them to look at. They see it with the notification."
                placeholder="The apex of the right lung; the client reports a cough of six weeks."
                autosize
                minRows={2}
                value={state.escalateNote}
                onChange={(e) => state.setEscalateNote(e.currentTarget.value)}
              />
            )}

            {state.decision === 'approved_with_adjustment' && (
              <NumberInput
                mt="md"
                label="Final monthly premium (BDT)"
                description={
                  data.plan?.monthlyPremiumBdt != null
                    ? `Plan suggests ৳${Math.round(
                        data.plan.monthlyPremiumBdt,
                      ).toLocaleString('en-IN')} for the cover requested. Adjust as you see fit.`
                    : 'Set the rate you are approving at.'
                }
                placeholder="7,500"
                thousandSeparator=","
                min={0}
                value={state.premium}
                onChange={(v) =>
                  state.setPremium(typeof v === 'number' ? v : Number(v) || undefined)
                }
              />
            )}

            <Group justify="space-between" mt="md">
              <Text size="xs" c="dimmed">
                There is no decline here. If this should not be approved, escalate it.
              </Text>
              <Button
                size="xs"
                disabled={
                  !state.decision ||
                  // An adjusted approval without a rate is not a decision.
                  (state.decision === 'approved_with_adjustment' && (state.premium ?? 0) <= 0)
                }
                onClick={() => state.submit.mutate()}
                loading={state.submit.isPending}
              >
                {state.decision === 'escalated_senior_review' ? 'Hand over' : 'Record decision'}
              </Button>
            </Group>
          </>
        )}
      </Paper>

      <AuditTrail applicationId={data.id} />
    </Stack>
  )
}

const bdt = (n: number) => `৳${Math.round(n).toLocaleString('en-IN')}`

/**
 * Mortality relative to age, from the blood panel and the lifestyle answers.
 *
 * Two readings, each a hazard ratio against a typical peer of the same age
 * and sex, and the higher governs. The first is Levine's published Phenotypic
 * Age: nine markers become the age whose average mortality matches this panel,
 * and each marker's share of the gap is shown in years. The second is our own
 * survival model, trained on NHANES with real death records; it reads whatever
 * was entered, including lifestyle, and each entered value is shown as the
 * hazard factor it carries against the peer's value. A single abnormal RDW
 * moves the formula more than anything else — that is the formula, not a bug,
 * and it is why every value sits next to its effect.
 */
interface MortalityDetails {
  chronological_age?: number
  mortality_ratio?: number
  governing?: 'phenotypic_age' | 'survival_model'
  ratios?: Record<string, number>
  standard_max_ratio?: number
  senior_min_ratio?: number
  phenotypic?: {
    phenotypic_age: number
    acceleration_years: number
    mortality_ratio: number
    contributions: Record<string, number>
    scorer?: string
    validation?: string
  } | null
  phenotypic_missing?: string[] | null
  survival?: {
    hazard_ratio_vs_peer: number
    peer: string
    factors: Record<string, number>
    inputs_used: string[]
    scorer?: string
    validation?: string
  } | null
  inputs?: Record<string, number | boolean | string>
  labels?: Record<string, string>
  reference?: Record<string, number>
  readings?: {
    key: string
    label: string
    value: number
    unit: string
    category: string
    flag: boolean
    note: string
  }[]
}

// The lifestyle and vitals keys the survival model may read, worded for the screen.
const FACTOR_LABELS: Record<string, string> = {
  height_cm: 'height',
  weight_kg: 'weight',
  smoker: 'smoking',
  alcohol: 'alcohol',
  activity: 'physical activity',
  sbp_mmhg: 'systolic blood pressure',
  ast_u_l: 'AST',
  alt_u_l: 'ALT',
  platelets_10e3_ul: 'platelets',
}

function MortalityPanel({ run }: { run: ArmRun }) {
  const d = run.details as MortalityDetails

  if (run.error || d.mortality_ratio == null) {
    return (
      <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
        <Text fw={600} size="sm">
          Blood panel and lifestyle
        </Text>
        <Text size="sm" c="dimmed" mt={4}>
          Could not be assessed: {run.error ?? 'no result was stored'}.
        </Text>
      </Paper>
    )
  }

  const ratio = d.mortality_ratio
  const elevated = ratio > 1
  const pheno = d.phenotypic
  const survival = d.survival
  const gap = pheno?.acceleration_years ?? 0
  const contributions = Object.entries(pheno?.contributions ?? {}).sort(
    (a, b) => Math.abs(b[1]) - Math.abs(a[1]),
  )
  const scale = Math.max(...contributions.map(([, y]) => Math.abs(y)), 0.5)
  // Factors within 5% of the peer say nothing worth a chip.
  const factors = Object.entries(survival?.factors ?? {})
    .filter(([, f]) => Math.abs(f - 1) >= 0.05)
    .sort((a, b) => Math.abs(b[1] - 1) - Math.abs(a[1] - 1))
  const label = (key: string) =>
    FACTOR_LABELS[key] ?? d.labels?.[key]?.split(',')[0] ?? key

  return (
    <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
      <Group justify="space-between" align="flex-start" mb="sm">
        <div>
          <Text fw={600} size="sm">
            Mortality relative to age
          </Text>
          <Text size="xs" c="dimmed">
            From the blood panel and lifestyle answers, against a typical peer of the same age
            and sex
          </Text>
        </div>
        {run.score != null && (
          <Badge variant="light" color={elevated ? 'orange' : 'teal'} size="lg">
            arm score {run.score.toFixed(1)}
          </Badge>
        )}
      </Group>

      <Text size="sm">
        Mortality about{' '}
        <Text span fw={700} c={elevated ? 'orange' : 'teal'}>
          {ratio.toFixed(2)}×
        </Text>{' '}
        that of a peer
        {d.governing === 'phenotypic_age' && ', by the published formula'}
        {d.governing === 'survival_model' && ', by the survival model'}. Standard rates run to{' '}
        {d.standard_max_ratio ?? 1.25}×; above {d.senior_min_ratio ?? 2}× a senior underwriter
        reviews.
      </Text>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md" mt="md">
        {/* ── Reading 1: the published formula ─────────────────── */}
        <Paper p="sm" bd="1px solid var(--mantine-color-dark-4)">
          <Group justify="space-between" mb="xs">
            <Text size="xs" fw={600} tt="uppercase" lts={0.4} c="dimmed">
              Phenotypic age
            </Text>
            {pheno && (
              <Badge size="xs" variant="light" color={pheno.mortality_ratio > 1 ? 'orange' : 'teal'}>
                {pheno.mortality_ratio.toFixed(2)}×
              </Badge>
            )}
          </Group>
          {pheno ? (
            <>
              <SimpleGrid cols={3} spacing="sm">
                <Field label="Age">{d.chronological_age}</Field>
                <Field label="Phenotypic">{pheno.phenotypic_age.toFixed(1)}</Field>
                <Field label="Gap">
                  <Text span c={gap > 0 ? 'orange' : 'teal'} fw={700}>
                    {gap >= 0 ? '+' : ''}
                    {gap.toFixed(1)} y
                  </Text>
                </Field>
              </SimpleGrid>
              <Stack gap={6} mt="sm">
                <Text size="xs" c="dimmed">
                  Years each value adds, against a typical adult
                </Text>
                {contributions.map(([key, years]) => (
                  <div key={key}>
                    <Group justify="space-between" mb={2} wrap="nowrap">
                      <Text size="xs" className="hl-ellipsis">
                        {d.labels?.[key] ?? key}
                        <Text span c="dimmed">
                          {' '}
                          · {String(d.inputs?.[key])}
                          {d.reference?.[key] != null && ` (typical ${d.reference[key]})`}
                        </Text>
                      </Text>
                      <Text size="xs" ff="monospace" c={years > 0 ? 'orange' : 'teal'}>
                        {years >= 0 ? '+' : ''}
                        {years.toFixed(1)}
                      </Text>
                    </Group>
                    <Box
                      h={4}
                      w="100%"
                      style={{ backgroundColor: 'var(--mantine-color-dark-5)', borderRadius: 2 }}
                    >
                      <Box
                        h="100%"
                        style={{
                          width: `${Math.min((Math.abs(years) / scale) * 100, 100)}%`,
                          backgroundColor: years > 0
                            ? 'var(--mantine-color-orange-5)'
                            : 'var(--mantine-color-teal-5)',
                          borderRadius: 2,
                        }}
                      />
                    </Box>
                  </div>
                ))}
              </Stack>
              {pheno.validation && (
                <Text size="xs" c="yellow.7" mt="sm">
                  {pheno.validation}
                </Text>
              )}
            </>
          ) : (
            <Text size="xs" c="dimmed">
              Needs all nine blood values.{' '}
              {(d.phenotypic_missing ?? []).length > 0 && (
                <>Missing: {(d.phenotypic_missing ?? []).map((p) => p.split(',')[0]).join(', ')}.</>
              )}
            </Text>
          )}
        </Paper>

        {/* ── Reading 2: the survival model ────────────────────── */}
        <Paper p="sm" bd="1px solid var(--mantine-color-dark-4)">
          <Group justify="space-between" mb="xs">
            <Text size="xs" fw={600} tt="uppercase" lts={0.4} c="dimmed">
              Survival model
            </Text>
            {survival && (
              <Badge
                size="xs"
                variant="light"
                color={survival.hazard_ratio_vs_peer > 1 ? 'orange' : 'teal'}
              >
                {survival.hazard_ratio_vs_peer.toFixed(2)}×
              </Badge>
            )}
          </Group>
          {survival ? (
            <>
              <Text size="xs" c="dimmed">
                Against {survival.peer}, measured on the same {survival.inputs_used.length} values.
              </Text>
              {factors.length > 0 ? (
                <Group gap={6} mt="sm">
                  {factors.map(([key, f]) => (
                    <Tooltip
                      key={key}
                      label={`${label(key)}: ${String(d.inputs?.[key])} — hazard ×${f.toFixed(2)} against the peer's value`}
                      withArrow
                    >
                      <Badge size="sm" variant="light" color={f > 1 ? 'orange' : 'teal'} ff="monospace">
                        {label(key)} ×{f.toFixed(2)}
                      </Badge>
                    </Tooltip>
                  ))}
                </Group>
              ) : (
                <Text size="xs" c="dimmed" mt="sm">
                  Nothing entered differs from the peer by more than 5%.
                </Text>
              )}
              {survival.validation && (
                <Text size="xs" c="yellow.7" mt="sm">
                  {survival.validation}
                </Text>
              )}
            </>
          ) : (
            <Text size="xs" c="dimmed">
              Not given: the survival model needs the applicant's sex and at least one entered value.
            </Text>
          )}
        </Paper>
      </SimpleGrid>

      {(d.readings ?? []).length > 0 && (
        <Stack gap="xs" mt="md">
          <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.4}>
            Standard readings from the same panel
          </Text>
          <Table fz="xs" withRowBorders={false} verticalSpacing={4}>
            <Table.Tbody>
              {(d.readings ?? []).map((r) => (
                <Table.Tr key={r.key}>
                  <Table.Td>
                    <Tooltip label={r.note} multiline w={320} withArrow>
                      <Text size="xs" style={{ cursor: 'help' }}>
                        {r.label}
                      </Text>
                    </Tooltip>
                  </Table.Td>
                  <Table.Td ff="monospace">
                    {r.value} {r.unit}
                  </Table.Td>
                  <Table.Td>
                    <Badge size="xs" variant="light" color={r.flag ? 'orange' : 'teal'}>
                      {r.category}
                    </Badge>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          <Text size="xs" c="dimmed">
            Published formulas (CKD-EPI 2021, FIB-4, WHO Asian BMI cut-offs, ADA glucose
            thresholds). They carry no weight of their own.
          </Text>
        </Stack>
      )}

      <Text size="xs" c="dimmed" mt="md">
        Relative to a same-age, same-sex peer under a US calibration. Not an absolute
        probability, not validated in South Asia, and not a diagnosis. The smoking box reads
        "current or former"; the model learned "current", so a former smoker is scored as one.
      </Text>
    </Paper>
  )
}

// What the Mirai arm stores per run (`apps/api/app/arms/mirai.py`).
interface MiraiDetails {
  risk_by_year?: number[]
  five_year_risk?: number
  views?: string[]
  anchors?: { low_tier_top: [number, number]; senior_review: [number, number] }
  server?: { model_name?: string | null; onconet_version?: string | null }
  scorer?: string
  validation?: string
}

/**
 * Any reader without a panel of its own: its score, its findings if it
 * reported some, and its error if it failed.
 *
 * The chest and retina readers land here. Their findings used to go to the one
 * shared box above, which kept whichever scored highest — so a chest film's 18
 * findings disappeared whenever a retinal photo outscored it.
 */
function ReaderPanel({ run }: { run: ArmRun }) {
  const details = (run.details ?? {}) as {
    findings?: Record<string, number>
    contributions?: Record<string, number>
    scorer?: string
    validation?: string
  }
  const probabilities = details.findings ?? {}
  const contributions = details.contributions ?? {}
  const labels = Array.from(new Set([...Object.keys(probabilities), ...Object.keys(contributions)]))
  const ranked = labels
    .map((label) => ({
      label,
      probability: probabilities[label] ?? 0,
      contribution: contributions[label] ?? 0,
    }))
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, TOP_N)
  const scale = Math.max(...ranked.map((f) => Math.abs(f.contribution)), 0.01)

  return (
    <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
      <Group justify="space-between" align="flex-start" mb="sm">
        <div>
          <Text fw={600} size="sm">
            {READER_LABELS[run.arm] ?? run.arm}
          </Text>
          <Text size="xs" style={{ color: 'var(--neo-muted)' }}>
            {run.version}
          </Text>
        </div>
        {run.score != null && (
          <Badge variant="light" size="lg" color={run.score > 65 ? 'red' : run.score > 30 ? 'yellow' : 'teal'}>
            {run.score.toFixed(1)}
          </Badge>
        )}
      </Group>

      {run.error ? (
        <Text size="sm" c="dimmed">
          Could not be assessed: {run.error}.
        </Text>
      ) : ranked.length > 0 ? (
        <>
          <Text size="xs" mb="sm" style={{ color: 'var(--neo-muted)' }}>
            What this reader found, ranked by how much each finding moved its score.
          </Text>
          <Stack gap="sm">
            {ranked.map((f) => (
              <FindingBar key={f.label} finding={f} scale={scale} />
            ))}
          </Stack>
        </>
      ) : (
        <Text size="sm" c="dimmed">
          No findings were reported.
        </Text>
      )}

      {details.validation && (
        <Text size="xs" c="yellow.7" mt="sm">
          {details.validation}
        </Text>
      )}
    </Paper>
  )
}

/** What each reader is called on screen. */
const READER_LABELS: Record<string, string> = {
  tb_xray: 'Chest X-ray',
  dr_fundus: 'Retinal photo',
  ecg_12lead: '12-lead ECG',
  mirai: 'Mammogram',
  medication_check: 'Clinical note',
  mortality: 'Blood panel and lifestyle',
}

function MiraiPanel({ run }: { run: ArmRun }) {
  const d = run.details as MiraiDetails
  const risks = d.risk_by_year ?? []
  const five = d.five_year_risk
  const average = d.anchors?.low_tier_top[0] ?? 0.017
  const high = d.anchors?.senior_review[0] ?? 0.045
  const elevated = five != null && five >= high
  const peak = Math.max(high, ...risks)

  return (
    <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
      <Group justify="space-between" align="flex-start" mb="sm">
        <div>
          <Text fw={600} size="sm">
            Breast-cancer risk from the mammogram
          </Text>
          <Text size="xs" c="dimmed">
            Mirai reads the four views and estimates the chance of a diagnosis within one to five
            years
          </Text>
        </div>
        {run.score != null && (
          <Badge variant="light" color={elevated ? 'orange' : five != null && five > average ? 'yellow' : 'teal'} size="lg">
            arm score {run.score.toFixed(1)}
          </Badge>
        )}
      </Group>

      {run.error || five == null ? (
        <Text size="sm" c="dimmed">
          Could not be assessed: {run.error ?? 'no result was stored'}.
        </Text>
      ) : (
        <>
          <Text size="sm">
            Five-year risk{' '}
            <Text span fw={700} c={elevated ? 'orange' : five > average ? 'yellow.7' : 'teal'}>
              {(five * 100).toFixed(1)}%
            </Text>
            . An average woman of screening age carries about {(average * 100).toFixed(1)}%; above{' '}
            {(high * 100).toFixed(1)}% is the high-risk group Mirai was built to find, and a senior
            underwriter reviews.
          </Text>

          <Stack gap={6} mt="md">
            {risks.map((r, i) => (
              <div key={i}>
                <Group justify="space-between" mb={2} wrap="nowrap">
                  <Text size="xs">Within {i + 1} year{i ? 's' : ''}</Text>
                  <Text size="xs" ff="monospace" c={r >= high ? 'orange' : 'dimmed'}>
                    {(r * 100).toFixed(2)}%
                  </Text>
                </Group>
                <Box h={6} w="100%" style={{ position: 'relative', backgroundColor: 'var(--mantine-color-dark-5)', borderRadius: 3 }}>
                  <Box
                    h="100%"
                    style={{
                      width: `${Math.min(100, (r / peak) * 100)}%`,
                      backgroundColor: r >= high ? 'var(--mantine-color-orange-5)' : 'var(--mantine-color-clinical-3)',
                      borderRadius: 3,
                    }}
                  />
                  <Box
                    style={{
                      position: 'absolute',
                      left: `${Math.min(100, (average / peak) * 100)}%`,
                      top: -2,
                      width: 1,
                      height: 10,
                      backgroundColor: 'var(--mantine-color-gray-5)',
                    }}
                  />
                </Box>
              </div>
            ))}
          </Stack>
          <Text size="xs" c="dimmed" mt="xs">
            The tick is the average five-year risk. Views read: {(d.views ?? []).join(', ')}.
          </Text>
        </>
      )}

      <Text size="xs" c="dimmed" mt="md">
        {d.scorer}
        {d.server?.model_name ? ` (${d.server.model_name}, onconet ${d.server.onconet_version})` : ''}.{' '}
        {d.validation}. A risk estimate, not a finding on the film: nothing here says where to look.
      </Text>
    </Paper>
  )
}

// What the medication check stores per run (`apps/api/app/arms/medication_check.py`).
interface MedicationDetails {
  medications?: {
    generic: string
    atc?: string | null
    as_written: string[]
    assertion: 'PRESENT' | 'PAST'
    conditions: string[]
    condition_labels: string[]
    declared: string[]
    ambiguous: boolean
    status: 'undisclosed' | 'explained' | 'immaterial'
    note?: string | null
    sentence: string
  }[]
  undisclosed?: {
    condition: string
    label: string
    medications: string[]
    points: number
    asked_on_form: boolean
  }[]
  explained?: string[]
  immaterial?: string[]
  excluded?: { generic: string; as_written: string; assertion: string; sentence: string }[]
  declared_labels?: string[]
  characters?: number
  scorer?: string
  validation?: string
}

const ASSERTION_WORDS: Record<string, string> = {
  NEGATED: 'ruled out or an allergy',
  FAMILY_HISTORY: "a relative's, not the applicant's",
  HYPOTHETICAL: 'proposed or conditional, not prescribed',
}

function MedicationPanel({ run, noteId }: { run: ArmRun; noteId: string | null }) {
  const d = run.details as MedicationDetails
  const [showNote, setShowNote] = useState(false)
  const noteText = useQuery({
    queryKey: ['note-text', noteId],
    queryFn: async () => {
      const response = await fetch(fileUrl(noteId!), { credentials: 'include' })
      if (!response.ok) throw new Error(`The note could not be loaded (${response.status}).`)
      return response.text()
    },
    enabled: showNote && Boolean(noteId),
    staleTime: Infinity,
  })

  const flags = d.undisclosed ?? []
  const meds = d.medications ?? []
  const excluded = d.excluded ?? []

  return (
    <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
      <Group justify="space-between" align="flex-start" mb="sm">
        <div>
          <Text fw={600} size="sm">
            Medications against the declared history
          </Text>
          <Text size="xs" c="dimmed">
            Each prescription in the note, what it is prescribed for, and whether the form said
            so
          </Text>
        </div>
        {run.score != null && (
          <Badge variant="light" color={flags.length ? 'orange' : 'teal'} size="lg">
            arm score {run.score.toFixed(1)}
          </Badge>
        )}
      </Group>

      {run.error ? (
        <Text size="sm" c="dimmed">
          Not checked: {run.error}.
        </Text>
      ) : flags.length === 0 ? (
        <Text size="sm">
          Every medication found is explained by the declared history or implies nothing
          material.
        </Text>
      ) : (
        <Stack gap={6}>
          {flags.map((f) => (
            <Group key={f.condition} gap="sm" wrap="nowrap" align="flex-start">
              <Badge size="sm" variant="light" color="orange" ff="monospace" miw={44}>
                {f.points.toFixed(0)}
              </Badge>
              <Text size="sm" style={{ flex: 1 }}>
                <Text span fw={600}>
                  {f.label}
                </Text>{' '}
                — implied by {f.medications.join(', ')}.{' '}
                <Text span c="dimmed">
                  {f.asked_on_form
                    ? 'The form asks about this and it was not declared: ask the applicant.'
                    : 'The form does not ask about this: ask the applicant.'}
                </Text>
              </Text>
            </Group>
          ))}
        </Stack>
      )}

      {meds.length > 0 && (
        <Table fz="xs" withRowBorders={false} verticalSpacing={4} mt="md">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Medication</Table.Th>
              <Table.Th>As written</Table.Th>
              <Table.Th>Prescribed for</Table.Th>
              <Table.Th></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {meds.map((m) => (
              <Table.Tr key={m.generic}>
                <Table.Td>
                  <Tooltip label={m.sentence} multiline w={360} withArrow>
                    <Text size="xs" style={{ cursor: 'help' }}>
                      {m.generic}
                      {m.assertion === 'PAST' && (
                        <Text span c="dimmed">
                          {' '}
                          (stopped)
                        </Text>
                      )}
                    </Text>
                  </Tooltip>
                </Table.Td>
                <Table.Td ff="monospace">{m.as_written.join(', ')}</Table.Td>
                <Table.Td>
                  {m.condition_labels.length ? m.condition_labels.join(' / ') : '—'}
                  {m.ambiguous && (
                    <Text span c="dimmed">
                      {' '}
                      · several uses
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Badge
                    size="xs"
                    variant="light"
                    color={
                      m.status === 'undisclosed' ? 'orange' : m.status === 'explained' ? 'teal' : 'gray'
                    }
                  >
                    {m.status === 'undisclosed'
                      ? 'not declared'
                      : m.status === 'explained'
                        ? 'declared'
                        : 'nothing material'}
                  </Badge>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      {excluded.length > 0 && (
        <Text size="xs" c="dimmed" mt="sm">
          Not counted:{' '}
          {excluded
            .map((e) => `${e.as_written} (${ASSERTION_WORDS[e.assertion] ?? e.assertion})`)
            .join('; ')}
          .
        </Text>
      )}

      {(d.declared_labels ?? []).length > 0 && (
        <Text size="xs" c="dimmed" mt="xs">
          Declared on the form: {d.declared_labels!.join(', ')}.
        </Text>
      )}

      {noteId && (
        <Stack gap="xs" mt="md">
          <Button
            variant="subtle"
            size="xs"
            onClick={() => setShowNote(!showNote)}
            rightSection={<IconChevronDown size={14} />}
            style={{ alignSelf: 'flex-start' }}
          >
            {showNote ? 'Hide the note' : 'Read the note'}
          </Button>
          {showNote && (
            <Box
              p="sm"
              mah={320}
              style={{
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
                fontFamily: 'var(--mantine-font-family-monospace)',
                fontSize: 12,
                backgroundColor: 'var(--mantine-color-dark-6)',
                borderRadius: 'var(--mantine-radius-sm)',
              }}
            >
              {noteText.isLoading
                ? 'Loading…'
                : noteText.error
                  ? String(noteText.error)
                  : noteText.data}
            </Box>
          )}
        </Stack>
      )}

      <Text size="xs" c="dimmed" mt="md">
        {d.scorer}. {d.validation}. The note is not de-identified and is shown here only to the
        underwriter holding the case.
      </Text>
    </Paper>
  )
}

// What the ECG arm stores per run (`apps/api/app/arms/ecg_12lead.py`).
interface EcgDetails {
  probabilities?: Record<string, number>
  thresholds?: Record<string, number>
  weights?: Record<string, number>
  labels?: Record<string, string>
  reported?: string[]
  reported_labels?: string[]
  focus?: string
  ecg_age?: number
  age_calibration?: { slope: number; intercept: number; mae_years: number; notable_gap_years: number }
  age_validation?: string
  scorer?: string
  validation?: string
}

function EcgPanel({ run, age }: { run: ArmRun; age: number | null }) {
  const d = run.details as EcgDetails

  if (run.error || !d.probabilities) {
    return (
      <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
        <Text fw={600} size="sm">
          12-lead ECG
        </Text>
        <Text size="sm" c="dimmed" mt={4}>
          Could not be read: {run.error ?? 'no result was stored'}.
        </Text>
      </Paper>
    )
  }

  const reported = d.reported ?? []
  const classes = Object.keys(d.probabilities)
  // Reported first, then by how close the rest came to their threshold.
  const ordered = [...classes].sort((a, b) => {
    const ra = reported.includes(a) ? 1 : 0
    const rb = reported.includes(b) ? 1 : 0
    if (ra !== rb) return rb - ra
    const ca = (d.probabilities?.[a] ?? 0) / (d.thresholds?.[a] ?? 1)
    const cb = (d.probabilities?.[b] ?? 0) / (d.thresholds?.[b] ?? 1)
    return cb - ca
  })

  // The age model is imprecise (MAE about 12 years on the public test set), so
  // the gap is measured against what it reads for a typical person of this age,
  // and only a gap past the paper's eight years is worth a word.
  const fit = d.age_calibration
  const expected = age != null && fit ? fit.slope * age + fit.intercept : null
  const gap = d.ecg_age != null && expected != null ? d.ecg_age - expected : null
  const notable = gap != null && fit ? Math.abs(gap) >= fit.notable_gap_years : false

  return (
    <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
      <Group justify="space-between" align="flex-start" mb="sm">
        <div>
          <Text fw={600} size="sm">
            12-lead ECG
          </Text>
          <Text size="xs" c="dimmed">
            Six rhythm and conduction abnormalities at the authors' operating thresholds, and an
            ECG age
          </Text>
        </div>
        {run.score != null && (
          <Badge variant="light" color={reported.length ? 'orange' : 'teal'} size="lg">
            arm score {run.score.toFixed(1)}
          </Badge>
        )}
      </Group>

      <Text size="sm">
        {reported.length === 0 ? (
          <>None of the six abnormalities reported.</>
        ) : (
          <>
            Reported:{' '}
            <Text span fw={700} c="orange">
              {(d.reported_labels ?? reported).join(', ')}
            </Text>
            .
          </>
        )}
      </Text>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md" mt="md">
        <Paper p="sm" bd="1px solid var(--mantine-color-dark-4)">
          <Text size="xs" fw={600} tt="uppercase" lts={0.4} c="dimmed" mb="xs">
            Probability against threshold
          </Text>
          <Stack gap={6}>
            {ordered.map((c) => {
              const p = d.probabilities?.[c] ?? 0
              const thr = d.thresholds?.[c] ?? 0.5
              const hit = reported.includes(c)
              // The bar runs to the threshold at 50% width, so "over the line"
              // is visible without reading the numbers.
              const width = Math.min(100, (p / thr) * 50)
              return (
                <div key={c}>
                  <Group justify="space-between" mb={2} wrap="nowrap">
                    <Text size="xs" className="hl-ellipsis" fw={hit ? 600 : 400}>
                      {d.labels?.[c] ?? c}
                      {c === d.focus && (
                        <Text span c="dimmed">
                          {' '}
                          · shaded on the tracing
                        </Text>
                      )}
                    </Text>
                    <Text size="xs" ff="monospace" c={hit ? 'orange' : 'dimmed'}>
                      {p.toFixed(3)} / {thr.toFixed(3)}
                    </Text>
                  </Group>
                  <Box h={6} w="100%" style={{ position: 'relative', backgroundColor: 'var(--mantine-color-dark-5)', borderRadius: 3 }}>
                    <Box
                      h="100%"
                      style={{
                        width: `${width}%`,
                        backgroundColor: hit ? 'var(--mantine-color-orange-5)' : 'var(--mantine-color-dark-3)',
                        borderRadius: 3,
                      }}
                    />
                    <Box
                      style={{
                        position: 'absolute',
                        left: '50%',
                        top: -2,
                        width: 1,
                        height: 10,
                        backgroundColor: 'var(--mantine-color-gray-5)',
                      }}
                    />
                  </Box>
                </div>
              )
            })}
          </Stack>
          <Text size="xs" c="dimmed" mt="sm">
            The tick is each abnormality's own threshold, recovered from the authors' published
            decisions; a reading past it is reported. Weights out of 100:{' '}
            {Object.entries(d.weights ?? {})
              .map(([c, w]) => `${d.labels?.[c] ?? c} ${Math.round(w * 100)}`)
              .join(', ')}
            .
          </Text>
        </Paper>

        <Paper p="sm" bd="1px solid var(--mantine-color-dark-4)">
          <Group justify="space-between" mb="xs">
            <Text size="xs" fw={600} tt="uppercase" lts={0.4} c="dimmed">
              ECG age
            </Text>
            {gap != null && (
              <Badge size="xs" variant="light" color={notable && gap > 0 ? 'orange' : 'teal'}>
                {gap >= 0 ? '+' : ''}
                {gap.toFixed(0)} y vs typical
              </Badge>
            )}
          </Group>
          <SimpleGrid cols={3} spacing="sm">
            <Field label="Age">{age ?? '—'}</Field>
            <Field label="ECG reads">{d.ecg_age != null ? d.ecg_age.toFixed(0) : '—'}</Field>
            <Field label="Typical read">{expected != null ? expected.toFixed(0) : '—'}</Field>
          </SimpleGrid>
          <Text size="xs" c="dimmed" mt="sm">
            {notable && gap != null && gap > 0
              ? `The tracing reads ${gap.toFixed(0)} years older than the model reads for a typical person of this age. In the paper, an ECG age more than eight years above the true age carried 1.79× the mortality. A prompt to look, not part of the score.`
              : 'Within the range the model reads for a typical person of this age. Not part of the score.'}
          </Text>
          {d.age_validation && (
            <Text size="xs" c="yellow.7" mt="xs">
              {d.age_validation}
            </Text>
          )}
        </Paper>
      </SimpleGrid>

      <Text size="xs" c="dimmed" mt="md">
        {d.scorer}. {d.validation}. Trained on Brazilian tracings; not a diagnosis, and a
        reported abnormality is a reason to obtain the cardiologist's report.
      </Text>
    </Paper>
  )
}

/**
 * What the tier means for the policy, priced against the cover the applicant
 * asked for.
 *
 * The premiums come from Idea.md §5, which gives a monthly figure per tier but
 * no rate card. The API treats those figures as the premium at a reference sum
 * assured and scales linearly, so asking for twice the cover doubles the
 * premium. That assumption is printed here rather than buried, because an
 * underwriter reading a number needs to know it is an illustration and not a
 * quote.
 */
function PlanPanel({
  plan,
  coverage,
}: {
  plan: Plan
  coverage: ApplicationDetail['coverage']
}) {
  const requested = coverage.coverageAmount ? Number(coverage.coverageAmount) : null

  return (
    <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
      <Group justify="space-between" align="flex-start" mb="sm">
        <div>
          <Text fw={600} size="sm">
            Recommended plan
          </Text>
          <Text size="xs" c="dimmed">
            What this tier is offered under your company's plans. A starting point for the rate, not the rate.
          </Text>
        </div>
        <Badge variant="light" color="clinical" size="lg">
          {plan.name}
        </Badge>
      </Group>

      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        <Field label="Cover requested">
          {requested ? bdt(requested) : '—'}
          {coverage.coverageType && (
            <Text span size="xs" c="dimmed">
              {' '}
              · {coverage.coverageType}
              {coverage.policyTerm ? `, ${coverage.policyTerm} yr` : ''}
            </Text>
          )}
        </Field>

        <Field label="Indicative monthly premium">
          {plan.monthlyPremiumBdt != null ? (
            bdt(plan.monthlyPremiumBdt)
          ) : (
            <Text span c="dimmed">
              Not quoted at this tier
            </Text>
          )}
        </Field>

        <Field label="Human step required">
          <Text span size="sm">
            {plan.humanStep}
          </Text>
        </Field>
      </SimpleGrid>

      <Text size="sm" mt="md">
        {plan.recommendation}.
        {plan.wellnessDiscountEligible && ' Eligible for a wellness-plan discount.'}
      </Text>

      <Text size="xs" c="dimmed" mt="xs">
        {plan.baseMonthlyBdt != null
          ? `Illustrative only: ${bdt(plan.baseMonthlyBdt)}/month at ${bdt(
              plan.referenceCoverBdt,
            )} of cover, scaled to the amount requested. Not an actuarial quote — you set the final rate.`
          : 'No rate is quoted at this tier. A medical professional decides what, if anything, is offered.'}
      </Text>
    </Paper>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.4}>
        {label}
      </Text>
      <Text size="sm" fw={600} mt={2}>
        {children}
      </Text>
    </div>
  )
}

function AuditTrail({ applicationId }: { applicationId: string }) {
  const { data } = useQuery({
    queryKey: ['audit', applicationId],
    queryFn: () => getAuditTrail(applicationId),
  })

  return (
    <details>
      <summary>
        <Text component="span" size="sm" c="dimmed">
          Audit trail{data ? ` (${data.entries.length})` : ''}
        </Text>
      </summary>
      <Paper bd="1px solid var(--mantine-color-default-border)" p="sm" mt="sm">
        {!data ? (
          <Text size="sm" c="dimmed">
            Loading…
          </Text>
        ) : (
          <Stack gap="sm">
            {/* The chain is re-verified on every read. An audit trail nobody
                checks is decoration. */}
            <Group gap="xs">
              {data.intact ? (
                <IconShieldCheck size={16} color="var(--mantine-color-teal-5)" />
              ) : (
                <IconShieldX size={16} color="var(--mantine-color-red-5)" />
              )}
              <Text size="xs" c={data.intact ? 'teal' : 'red'}>
                {data.intact
                  ? 'Hash chain verified — no entry has been altered.'
                  : `Chain broken: ${data.brokenAt}`}
              </Text>
            </Group>

            <Table.ScrollContainer minWidth={520}>
              <Table fz="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>When</Table.Th>
                    <Table.Th>Event</Table.Th>
                    <Table.Th>Who</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.entries.map((e) => (
                    <Table.Tr key={e.id}>
                      <Table.Td c="dimmed">{new Date(e.createdAt).toLocaleString()}</Table.Td>
                      <Table.Td ff="monospace">{e.eventType}</Table.Td>
                      <Table.Td>{e.actorName ?? 'system'}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Stack>
        )}
      </Paper>
    </details>
  )
}
