import {
  Alert,
  Badge,
  Box,
  Button,
  Center,
  Divider,
  Group,
  Image,
  Loader,
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
  fileUrl,
  fulfilEvidenceRequest,
  getApplication,
  getAuditTrail,
  recordDecision,
  requestEvidence,
  reviseTurnaround,
  type ApplicationDetail,
  type ArmRun,
  type DecisionType,
  type Finding,
  type Plan,
} from '../../api/client'
import { TierBadge, type Tier } from '../../components/TierBadge'
import { useAuth } from '../../context/AuthContext'

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
        style={{ backgroundColor: 'var(--mantine-color-dark-5)', borderRadius: 3 }}
      >
        <Box
          h="100%"
          style={{
            width: `${Math.min(width, 100)}%`,
            backgroundColor: toward
              ? 'var(--mantine-color-clinical-3)'
              : 'var(--mantine-color-dark-3)',
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

  const submit = useMutation({
    mutationFn: () =>
      recordDecision(id, {
        decision: decision as DecisionType,
        finalPremium: decision === 'approved_with_adjustment' ? premium : null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['application', id] })
      void queryClient.invalidateQueries({ queryKey: ['applications'] })
      void queryClient.invalidateQueries({ queryKey: ['audit', id] })
      notifications.show({ title: 'Decision recorded', message: 'It cannot be changed.', color: 'teal' })
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
    mutationFn: (documentId: string) => fulfilEvidenceRequest(id, documentId),
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
      <Center mih={300}>
        <Loader color="clinical" type="dots" />
      </Center>
    )
  }

  if (error || !data) {
    return (
      <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} />} title="Could not open this application">
        {error instanceof Error ? error.message : 'Unknown error'}
      </Alert>
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
  submit: { mutate: () => void; isPending: boolean }
  requestOpen: boolean
  setRequestOpen: (v: boolean) => void
  requestItems: string
  setRequestItems: (v: string) => void
  requestNote: string
  setRequestNote: (v: string) => void
  request: { mutate: () => void; isPending: boolean }
  receive: { mutate: (documentId: string) => void; isPending: boolean }
  reviseOpen: boolean
  setReviseOpen: (v: boolean) => void
  reviseDate: string
  setReviseDate: (v: string) => void
  reviseReason: string
  setReviseReason: (v: string) => void
  revise: { mutate: () => void; isPending: boolean }
}

/** Derive a human-readable image label from whichever arm produced the evidence. */
function imageLabelFor(modelsRequested: string[]): string {
  if (modelsRequested.includes('eyepacs')) return 'Retinal photo'
  return 'Chest X-ray'
}

function Review({ data, state }: { data: ApplicationDetail; state: ReviewState }) {
  const findings = data.findings ?? []
  const adjustments = data.adjustments ?? []
  const files = data.files ?? []
  const errors = data.errors ?? []

  const imageLabel = imageLabelFor(data.modelsRequested ?? [])

  const evidence = files.find((f) => f.kind === 'evidence')
  const heatmap = files.find((f) => f.kind === 'gradcam')
  const heatmapAvailable = Boolean(heatmap)

  // Each arm's own report. The image and findings panels above belong to the
  // vision arm; an application scored from the blood panel alone has neither,
  // and showing "no image was stored" for it would read as a fault.
  const arms = data.arms ?? []
  const mortality = arms.find((a) => a.arm === 'mortality')
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
  const scored = data.status === 'scored' || data.status === 'decided'
  const pending = data.status === 'submitted' || data.status === 'processing'

  const { user } = useAuth()
  const isElevated = data.score?.tier === 'elevated'
  const isUnderwriter = user?.role === 'underwriter'
  const isMedical = user?.role === 'medical_professional'

  return (
    <Stack gap="md">
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
              <span className="hl-kv-label">Applicant</span>
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
              <div className="hl-kv" style={{ alignItems: 'flex-end' }}>
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

      {pending && (
        <Alert color="blue" variant="light" title="Still being evaluated">
          The model is reading the evidence now. This screen updates on its own.
        </Alert>
      )}

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
        {/* ── Left · the image ──────────────────────────────── */}
        <Paper p="sm" bd="1px solid var(--mantine-color-default-border)">
          <Group justify="space-between" mb="sm">
            <Text fw={600} size="sm">
              {imageLabel}
            </Text>
            <Switch
              label="Heatmap overlay"
              size="xs"
              checked={state.showHeatmap && heatmapAvailable}
              onChange={() => state.setShowHeatmap(!state.showHeatmap)}
              disabled={!heatmapAvailable}
            />
          </Group>

          <Box
            h={340}
            style={{
              display: 'grid',
              placeItems: 'center',
              backgroundColor: 'var(--mantine-color-dark-6)',
              borderRadius: 'var(--mantine-radius-sm)',
              overflow: 'hidden',
            }}
          >
            {evidence || heatmap ? (
              <Image
                src={fileUrl(state.showHeatmap && heatmap ? heatmap.id : (evidence ?? heatmap)!.id)}
                alt={state.showHeatmap ? `${imageLabel} with model heatmap` : imageLabel}
                h={340}
                fit="contain"
              />
            ) : (
              <Text c="dimmed" size="sm">
                No image was stored for this application.
              </Text>
            )}
          </Box>
          <Text size="xs" c="dimmed" mt="sm">
            {heatmapAvailable
              ? 'The overlay marks the region that moved the score most — not a diagnosis.'
              : 'No heatmap was produced for this image.'}
          </Text>
        </Paper>

        {/* ── Right · why this score ────────────────────────── */}
        <Stack gap="md">
          <Paper p="sm" bd="1px solid var(--mantine-color-default-border)">
            <Group justify="space-between" mb="sm">
              <Text fw={600} size="sm">
                What moved the score
              </Text>
              <Text size="xs" c="dimmed">
                {shown.length} of {findings.length} shown
              </Text>
            </Group>

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
            <Text fw={600} size="sm" mb="sm">
              What the declared history changed
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

      {/* ── The blood panel, against age ─────────────────────── */}
      {mortality && <MortalityPanel run={mortality} />}

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
                  <Badge size="xs" variant="light" color="teal">
                    Received
                  </Badge>
                ) : (
                  <Button
                    size="xs"
                    variant="light"
                    onClick={() => state.receive.mutate(doc.id)}
                    loading={state.receive.isPending}
                  >
                    Mark received
                  </Button>
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
          {isMedical ? (
            <Badge color="grape" variant="light" size="xs">
              Medical Professional Authority
            </Badge>
          ) : isUnderwriter ? (
            <Badge color="clinical" variant="light" size="xs">
              Underwriter Review
            </Badge>
          ) : null}
        </Group>

        {/* Medical Professional high-risk guidance */}
        {isMedical && isElevated && !decided && (
          <Alert
            color="grape"
            variant="light"
            icon={<IconShieldCheck size={18} />}
            title="Medical Professional Clinical Review"
            mb="sm"
          >
            <Text size="xs">
              This application has been scored as <strong>Tier 3 (Elevated Risk)</strong>. As a Medical Professional,
              you hold binding authority to audit sub-scores, review Grad-CAM heatmaps, apply actuarial rate adjustments, or finalize approval.
            </Text>
          </Alert>
        )}

        {/* Underwriter Tier 3 Mandatory Escalation Notice */}
        {isUnderwriter && isElevated && !decided && (
          <Alert
            color="red"
            variant="light"
            icon={<IconAlertTriangle size={18} />}
            title="Mandatory Escalation Required"
            mb="sm"
          >
            <Text size="xs">
              This application has an elevated risk score (Tier 3). Carrier governance requires mandatory escalation to a Medical Professional.
              Approval actions are disabled for junior underwriters on Tier 3 cases.
            </Text>
          </Alert>
        )}

        {decided ? (
          <Alert icon={<IconCircleCheck size={18} />} color="teal" variant="light" title="Decision recorded">
            <Text size="sm">
              <strong>
                {DECISIONS.find((d) => d.value === data.decision?.decision)?.label ??
                  data.decision?.decision}
              </strong>{' '}
              by {data.decision?.underwriterName ?? 'an underwriter'},{' '}
              {relativeTime(data.decision?.decidedAt)}.
              {data.decision?.finalPremium != null &&
                ` Final premium ${Number(data.decision.finalPremium).toLocaleString()}.`}{' '}
              Decisions are write-once and can no longer be edited.
            </Text>
          </Alert>
        ) : !scored && data.status !== 'insufficient_evidence' && data.status !== 'awaiting_evidence' ? (
          <Text size="sm" c="dimmed">
            A decision can be recorded once the evaluation finishes.
          </Text>
        ) : (
          <>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
              {DECISIONS.map((d) => {
                const isApprovalAction =
                  d.value === 'confirmed_fast_track' || d.value === 'approved_with_adjustment'
                const isBlockedForUnderwriter = isUnderwriter && isElevated && isApprovalAction
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
                      label="Tier 3 applications require escalation to a Medical Professional"
                      withArrow
                    >
                      <div>{btn}</div>
                    </Tooltip>
                  )
                }

                return btn
              })}
            </SimpleGrid>

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
                There is no reject button. Escalation to a human underwriter is the path.
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
                Submit decision
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
            What this risk tier means for the policy
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

function StatusBadge({ status }: { status: ApplicationDetail['status'] }) {
  const meta: Record<string, { label: string; color: string }> = {
    submitted: { label: 'Evaluation pending', color: 'gray' },
    processing: { label: 'Evaluating', color: 'blue' },
    scored: { label: 'Ready for review', color: 'teal' },
    insufficient_evidence: { label: 'More evidence needed', color: 'yellow' },
    awaiting_evidence: { label: 'Waiting on applicant', color: 'orange' },
    decided: { label: 'Decided', color: 'gray' },
  }
  const m = meta[status] ?? { label: status, color: 'gray' }
  return (
    <Badge color={m.color} variant="light" size="sm">
      {m.label}
    </Badge>
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
