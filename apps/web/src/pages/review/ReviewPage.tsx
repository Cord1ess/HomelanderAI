import {
  Alert,
  Anchor,
  FileButton,
  Badge,
  Box,
  Button,
  Divider,
  Grid,
  Group,
  Image,
  Paper,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Tabs,
  Text,
  ThemeIcon,
  Tooltip,
  Textarea,
  TextInput,
  Modal,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import {
  IconAlertTriangle,
  IconChevronDown,
  IconShieldCheck,
  IconShieldX,
} from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

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
} from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { StatusBadge } from '../../components/StatusBadge'
import { DoctorVerdictBadge } from '../../components/DoctorVerdictBadge'
import { PolicyPanel } from '../clients/PolicyPanel'
import { DecisionPanel } from './DecisionPanel'
import { DoctorPanel } from './DoctorPanel'
import { ReaderCards } from './ReaderCards'
import { groupRuns, infoFor, limitsOf, bandFor, type Limits } from './readers'
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
        })
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['application', id] })
      void queryClient.invalidateQueries({ queryKey: ['applications'] })
      void queryClient.invalidateQueries({ queryKey: ['audit', id] })
      if (decision === 'escalated_senior_review') {
        notifications.show({
          title: 'Handed to a doctor',
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
  const errors = data.errors ?? []

  const decided = Boolean(data.decision)
  const escalated = data.status === 'escalated'
  const pending = data.status === 'submitted' || data.status === 'processing'

  const { user } = useAuth()
  const isElevated = data.score?.tier === 'elevated'
  const isUnderwriter = user?.role === 'underwriter'
  const isMedical = user?.role === 'medical_professional'
  // The owner: decides anything, and may do a doctor's work too.
  const isAdmin = user?.role === 'admin'
  // The latest doctor's verdict, if a doctor has checked the results. It is
  // what lets an underwriter decide an elevated case.
  const latestReview = (data.doctorReviews ?? [])[0]
  const reviewedByDoctor = Boolean(latestReview)

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
              <DoctorVerdictBadge verdict={latestReview?.verdict} />
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

      {/* The readings on the left, what is done about them on the right. One
          page, one scroll bar: the right column used to scroll on its own and
          cut its last card off. Both columns run the same height, and the last
          card in each fills what is left, so their bottoms line up. */}
      <Grid gap="md" align="stretch">
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <div className="review-col">
            <Readings data={data} state={state} />
          </div>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Stack gap="md" className="review-col">
          {isMedical ? (
            <DoctorPanel data={data} />
          ) : (
          <>
          {/* With a doctor, the owner's first job here is likely the doctor's. */}
          {isAdmin && escalated && <DoctorPanel data={data} />}
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
            {escalated && !decided && (
              <Alert color="grape" variant="light" icon={<IconShieldCheck size={18} />} title="With a doctor" mb="sm">
                <Text size="xs">
                  {isAdmin
                    ? 'A doctor is checking the results. As the owner you can still decide now, or give the verdict yourself below.'
                    : 'A doctor is checking the results. You can decide once they send it back with their verdict.'}
                </Text>
              </Alert>
            )}

            {isUnderwriter && isElevated && !decided && !escalated && !reviewedByDoctor && (
              <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} />} title="Elevated risk" mb="sm">
                <Text size="xs">
                  The models put this application in the elevated tier. Send it to a doctor first;
                  once they have checked the results you can decide it.
                </Text>
              </Alert>
            )}

            {latestReview && !escalated && (
              <Alert
                color={latestReview.verdict === 'accurate' ? 'teal' : 'red'}
                variant="light"
                icon={<IconShieldCheck size={18} />}
                title={
                  latestReview.verdict === 'accurate'
                    ? 'Doctor verified: the results are correct'
                    : 'Doctor verified: the results are wrong'
                }
                mb="sm"
              >
                {latestReview.note && <Text size="xs">{latestReview.note}</Text>}
                <Text size="xs" c="dimmed" mt={latestReview.note ? 4 : 0}>
                  {latestReview.doctorName ?? 'A doctor'}, {relativeTime(latestReview.createdAt)}
                </Text>
              </Alert>
            )}

            <DecisionPanel data={data} isElevated={isElevated} reviewedByDoctor={reviewedByDoctor} />
          </Paper>
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
                decision stays open.
              </Text>
            </Paper>
          )}

          {/* The owner may do a doctor's work as well: check the results, or
              write to the client directly. */}
          {/* The policy this approval issued, with its payments. */}
          {data.policy && (
            <PolicyPanel policies={[data.policy]} clientId={data.policy.clientId} compact />
          )}
          {isAdmin && !escalated && <DoctorPanel data={data} />}
          </>
          )}
          </Stack>
        </Grid.Col>
      </Grid>

      <AuditTrail applicationId={data.id} />
    </Stack>
  )
}

// ── The readings: an overview, then one tab per reader ──────────────────────

function Readings({ data, state }: { data: ApplicationDetail; state: ReviewState }) {
  const limits = limitsOf(data)
  const groups = groupRuns(data.arms ?? [])
  const [params] = useSearchParams()
  const [picked, setPicked] = useState<string | null>(params.get('reader'))
  const active = picked && groups.some((g) => g.arm === picked) ? picked : (groups[0]?.arm ?? null)

  if (groups.length === 0) return null
  const adjustments = data.adjustments ?? []

  return (
    <Stack gap="md" className="review-col">
      <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
        <Group justify="space-between" align="baseline" mb="sm">
          <Text fw={600} size="sm">
            What each reader found
          </Text>
          <Text size="xs" c="dimmed">
            {groups.length} reader{groups.length === 1 ? '' : 's'} · select one to open it
          </Text>
        </Group>
        <ReaderCards groups={groups} limits={limits} active={active} onSelect={setPicked} />

        {/* The declared history moves the overall score, not any one reader's,
            so it sits with the overview rather than inside a reader. */}
        <Box mt="md" pt="sm" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }}>
          <Text size="xs" fw={600} tt="uppercase" lts={0.4} c="dimmed" mb={6}>
            Declared history · applied to the overall score
          </Text>
          {adjustments.length === 0 ? (
            <Text size="sm" c="dimmed">
              Nothing declared on the form changed the score.
            </Text>
          ) : (
            <Stack gap={4}>
              {adjustments.map((a) => (
                <Group key={a.key} gap="sm" wrap="nowrap" align="flex-start">
                  <Badge
                    size="sm"
                    variant="light"
                    color={a.points >= 0 ? 'orange' : 'teal'}
                    ff="monospace"
                    miw={44}
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
        </Box>
      </Paper>

      <Tabs value={active} onChange={setPicked} keepMounted={false}>
        <Tabs.List>
          {groups.map((g) => {
            const Icon = infoFor(g.arm).icon
            return (
              <Tabs.Tab key={g.arm} value={g.arm} leftSection={<Icon size={14} />}>
                {infoFor(g.arm).title}
              </Tabs.Tab>
            )
          })}
        </Tabs.List>
        {groups.map((g) => (
          <Tabs.Panel key={g.arm} value={g.arm} pt="md">
            <Stack gap="md">
              {g.runs.map((run, i) => (
                <ModelSection
                  key={`${run.arm}-${i}`}
                  run={run}
                  data={data}
                  state={state}
                  limits={limits}
                  reading={g.runs.length > 1 ? i + 1 : null}
                />
              ))}
            </Stack>
          </Tabs.Panel>
        ))}
      </Tabs>
    </Stack>
  )
}

/**
 * One reader, framed the same way as every other: what it read and its score,
 * its own evidence beside its result, then the figure that says how far to
 * trust it. A reader that failed says so in the same place for every reader.
 */
function ModelSection({
  run,
  data,
  state,
  limits,
  reading,
}: {
  run: ArmRun
  data: ApplicationDetail
  state: ReviewState
  limits: Limits
  reading: number | null
}) {
  const info = infoFor(run.arm)
  const band = bandFor(run.score, limits)
  const Icon = info.icon
  const files = data.files ?? []
  const isText = (f: EvidenceFile) => Boolean(f.mimeType?.startsWith('text/'))
  const images = info.evidenceKind
    ? files.filter((f) => f.kind === 'evidence' && f.evidenceKind === info.evidenceKind && !isText(f))
    : []
  const heatmaps = files.filter((f) => f.kind === 'gradcam')
  const heatmapFor = (image: EvidenceFile) =>
    heatmaps.find((h) => h.ofFileId === image.id) ??
    (heatmaps.length === 1 && images.length === 1 ? heatmaps[0] : undefined)
  const note = files.find((f) => f.kind === 'evidence' && isText(f))
  const details = (run.details ?? {}) as { scorer?: string; validation?: string }

  const body = (() => {
    switch (run.arm) {
      case 'tb_xray':
        return <ChestPanel run={run} state={state} />
      case 'dr_fundus':
        return <RetinaPanel run={run} />
      case 'ecg_12lead':
        return <EcgPanel run={run} age={ageAt(data.applicant.dateOfBirth, data.submittedAt)} />
      case 'mirai':
        return <MiraiPanel run={run} />
      case 'medication_check':
        return <MedicationPanel run={run} noteId={note?.id ?? null} />
      case 'mortality':
        return <MortalityPanel run={run} />
      default:
        return <ReaderPanel run={run} />
    }
  })()

  const evidence =
    run.arm === 'mirai' ? (
      <MammogramViews files={images} />
    ) : (
      <Stack gap="sm">
        {images.map((image) => (
          <EvidencePanel key={image.id} file={image} heatmap={heatmapFor(image)} />
        ))}
      </Stack>
    )

  return (
    <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
      <Group justify="space-between" align="flex-start" mb="md" wrap="nowrap">
        <Group gap="sm" wrap="nowrap" align="flex-start">
          <ThemeIcon variant="light" size="lg" radius="md">
            <Icon size={18} />
          </ThemeIcon>
          <div>
            <Text fw={700}>
              {info.title}
              {reading != null && (
                <Text span c="dimmed" fw={400}>
                  {' '}
                  · reading {reading}
                </Text>
              )}
            </Text>
            <Text size="xs" c="dimmed">
              {info.reads}
            </Text>
          </div>
        </Group>
        {band && run.score != null && (
          <Group gap="xs" wrap="nowrap" align="center">
            <Text fw={700} size="xl" ff="monospace">
              {run.score.toFixed(1)}
            </Text>
            <Badge variant="light" color={band.color} style={{ minWidth: 'max-content' }}>
              {band.label}
            </Badge>
          </Group>
        )}
      </Group>

      {run.error ? (
        <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={18} />} title="Could not be read">
          <Text size="sm">{run.error}</Text>
          <Text size="xs" c="dimmed" mt={4}>
            The application was scored on the other readers without this one.
          </Text>
        </Alert>
      ) : images.length === 0 ? (
        body
      ) : info.stacked ? (
        <Stack gap="md">
          {evidence}
          {body}
        </Stack>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          {evidence}
          <div>{body}</div>
        </SimpleGrid>
      )}

      {(details.scorer || details.validation) && (
        <Box mt="md" pt="sm" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }}>
          {details.scorer && (
            <Text size="xs" c="dimmed">
              {details.scorer}
            </Text>
          )}
          {details.validation && (
            <Text size="xs" c="yellow.7" mt={2}>
              {details.validation}
            </Text>
          )}
        </Box>
      )}
    </Paper>
  )
}

/** The chest reader: the findings that moved its TB score, strongest first. */
function ChestPanel({ run, state }: { run: ArmRun; state: ReviewState }) {
  const d = (run.details ?? {}) as {
    findings?: Record<string, number>
    contributions?: Record<string, number>
  }
  const probabilities = d.findings ?? {}
  const contributions = d.contributions ?? {}
  const ranked = Object.keys({ ...probabilities, ...contributions })
    .map((label) => ({
      label,
      probability: probabilities[label] ?? 0,
      contribution: contributions[label] ?? 0,
    }))
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
  const shown = state.showAll ? ranked : ranked.slice(0, TOP_N)
  const scale = Math.max(...ranked.map((f) => Math.abs(f.contribution)), 0.01)

  if (ranked.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        The model produced no findings.
      </Text>
    )
  }
  return (
    <div>
      <Text size="xs" mb="sm" c="dimmed">
        The network reports 18 general chest findings; a model trained on TB films weighs them
        into the score. Ranked by how much each moved it. The first figure is how sure the network
        is the finding is there; the second is its push on the score, up or down.
      </Text>
      <Stack gap="sm">
        {shown.map((f) => (
          <FindingBar key={f.label} finding={f} scale={scale} />
        ))}
      </Stack>
      {ranked.length > TOP_N && (
        <Button
          variant="subtle"
          size="xs"
          mt="sm"
          fullWidth
          rightSection={<IconChevronDown size={14} />}
          onClick={() => state.setShowAll(!state.showAll)}
        >
          {state.showAll ? `Show top ${TOP_N}` : `Show all ${ranked.length}`}
        </Button>
      )}
    </div>
  )
}

const ICDR_GRADES = ['No DR', 'Mild NPDR', 'Moderate NPDR', 'Severe NPDR', 'Proliferative DR']

/** The retina reader: the grade, how likely it is to need referral, and why. */
function RetinaPanel({ run }: { run: ArmRun }) {
  const d = (run.details ?? {}) as {
    grade_name?: string
    icdr_grade?: number
    referable_probability?: number
    class_probabilities?: Record<string, number>
  }
  const referable = d.referable_probability
  const classes = d.class_probabilities ?? {}

  return (
    <div>
      <SimpleGrid cols={2} spacing="sm">
        <Field label="Grade">{d.grade_name ?? '—'}</Field>
        <Field label="Needs referral">
          {referable != null ? (
            <Text span c={referable >= 0.5 ? 'orange' : 'teal'} fw={700}>
              {(referable * 100).toFixed(0)}%
            </Text>
          ) : (
            '—'
          )}
        </Field>
      </SimpleGrid>
      <Text size="xs" c="dimmed" mt="sm">
        Referable means moderate retinopathy or worse (ICDR grade 2+), the point at which an eye
        specialist should see the patient. The score is that probability.
      </Text>

      <Text size="xs" fw={600} tt="uppercase" lts={0.4} c="dimmed" mt="md" mb={6}>
        Probability of each grade
      </Text>
      {/* ICDR order, whatever order the stored probabilities came back in:
          the grades are a scale, and grade 2 onwards is what needs referral. */}
      <Stack gap={6}>
        {ICDR_GRADES.map((name, i) => {
          const p = classes[name] ?? 0
          const chosen = d.grade_name === name
          return (
            <div key={name}>
              <Group justify="space-between" mb={2} wrap="nowrap">
                <Text size="xs" fw={chosen ? 700 : 400}>
                  {name}
                </Text>
                <Text size="xs" ff="monospace" c={chosen ? undefined : 'dimmed'}>
                  {(p * 100).toFixed(1)}%
                </Text>
              </Group>
              <Box h={6} style={{ backgroundColor: 'var(--mantine-color-dark-5)', borderRadius: 3 }}>
                <Box
                  h="100%"
                  style={{
                    width: `${Math.min(100, p * 100)}%`,
                    backgroundColor:
                      i >= 2 ? 'var(--mantine-color-orange-5)' : 'var(--mantine-color-teal-5)',
                    borderRadius: 3,
                  }}
                />
              </Box>
            </div>
          )
        })}
      </Stack>
    </div>
  )
}

/** The four mammogram views, small, in the order a radiologist hangs them. */
function MammogramViews({ files }: { files: EvidenceFile[] }) {
  const position = (f: EvidenceFile) => {
    const name = `${f.filename ?? ''}`.toLowerCase()
    const right = /right|_r_|\br\b|-r-|rcc|rmlo/.test(name)
    const mlo = name.includes('mlo')
    return (right ? 0 : 1) + (mlo ? 2 : 0)
  }
  const sorted = [...files].sort((a, b) => position(a) - position(b))
  return (
    <SimpleGrid cols={2} spacing="xs">
      {sorted.map((f) => (
        <Box key={f.id}>
          <Box
            h={170}
            style={{
              display: 'grid',
              placeItems: 'center',
              backgroundColor: '#000',
              borderRadius: 'var(--mantine-radius-sm)',
              overflow: 'hidden',
            }}
          >
            <Image src={fileUrl(f.id)} alt={f.filename ?? 'Mammogram view'} h={170} fit="contain" />
          </Box>
          <Text size="xs" c="dimmed" mt={2} truncate>
            {f.filename}
          </Text>
        </Box>
      ))}
    </SimpleGrid>
  )
}

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

  if (d.mortality_ratio == null) {
    return (
      <Text size="sm" c="dimmed">
        No result was stored.
      </Text>
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
    <div>
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
    </div>
  )
}

// What the Mirai arm stores per run (`apps/api/app/arms/mirai.py`).
interface MiraiDetails {
  risk_by_year?: number[]
  five_year_risk?: number
  views?: string[]
  anchors?: { low_tier_top: [number, number]; senior_review: [number, number] }
  /** How long the model took, as the Mirai service measured it ("43.10s"). */
  runtime?: string | null
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

  return ranked.length > 0 ? (
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
      )
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
    <div>
      {five == null ? (
        <Text size="sm" c="dimmed">
          No result was stored.
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
        {d.runtime ? `Read on this machine in ${d.runtime}. ` : ''}A risk estimate, not a finding
        on the film: nothing here says where to look.
      </Text>
    </div>
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
    /** Which reader found it: "biobert", "table", or both. */
    found_by?: string[]
    /** BioBERT found a misspelling and the table matched it by similarity. */
    spelling?: boolean
  }[]
  undisclosed?: {
    condition: string
    label: string
    medications: string[]
    /** How the note itself names the condition, when it does. */
    stated?: string[]
    points: number
    asked_on_form: boolean
  }[]
  /** Drugs BioBERT found that the table does not list. */
  unlisted?: { as_written: string; assertion: string; sentence: string }[]
  /** Diagnoses BioBERT found written in the note. */
  conditions_in_note?: {
    as_written: string
    labels: string[]
    assertion: string
    declared: boolean
    sentence: string
  }[]
  /** Everything else BioBERT called a disease — symptoms, mostly. Never scored. */
  other_findings?: { as_written: string; assertion: string }[]
  biobert?: { drugs_found: number; diseases_found: number; models: Record<string, string> }
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
    <div>
      {flags.length === 0 ? (
        <Text size="sm">
          Everything BioBERT found in the note is explained by the declared history or implies
          nothing material.
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
                —{' '}
                {[
                  (f.stated ?? []).length
                    ? `written in the note as “${f.stated!.join('”, “')}”`
                    : null,
                  f.medications.length ? `implied by ${f.medications.join(', ')}` : null,
                ]
                  .filter(Boolean)
                  .join(', and ')}
                .{' '}
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
        <Table.ScrollContainer minWidth={720} mt="md">
        <Table fz="xs" withRowBorders={false} verticalSpacing={4}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Medication</Table.Th>
              <Table.Th>As written</Table.Th>
              <Table.Th>Prescribed for</Table.Th>
              <Table.Th>Found by</Table.Th>
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
                <Table.Td style={{ whiteSpace: 'nowrap' }}>
                  <Text size="xs">
                    {(m.found_by ?? []).includes('biobert')
                      ? (m.found_by ?? []).includes('table')
                        ? 'BioBERT + table'
                        : 'BioBERT'
                      : 'table (brand name)'}
                    {m.spelling && (
                      <Text span c="dimmed">
                        {' '}
                        · misspelt
                      </Text>
                    )}
                  </Text>
                </Table.Td>
                <Table.Td style={{ whiteSpace: 'nowrap' }}>
                  <Badge
                    size="xs"
                    variant="light"
                    // The badge clips its label, so its smallest width is a few letters and
                    // the cell shrank to that. Its full label is the smallest it may go.
                    style={{ minWidth: 'max-content' }}
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
        </Table.ScrollContainer>
      )}

      {(d.conditions_in_note ?? []).length > 0 && (
        <Text size="xs" mt="sm">
          <Text span fw={600}>
            Diagnoses written in the note:
          </Text>{' '}
          {d
            .conditions_in_note!.map((c) =>
              c.assertion === 'PRESENT' || c.assertion === 'PAST'
                ? `${c.as_written} (${c.declared ? 'declared' : 'not declared'})`
                : `${c.as_written} (${ASSERTION_WORDS[c.assertion] ?? c.assertion})`,
            )
            .join('; ')}
          .
        </Text>
      )}

      {(d.unlisted ?? []).length > 0 && (
        <Text size="xs" c="dimmed" mt="xs">
          BioBERT also found {d.unlisted!.map((u) => u.as_written).join(', ')} — not in the
          medication table, so nothing says what it is prescribed for and it is not scored. Worth a
          look.
        </Text>
      )}

      {(d.other_findings ?? []).length > 0 && (
        <Text size="xs" c="dimmed" mt="xs">
          Symptoms and other findings mentioned, not scored:{' '}
          {[...new Set(d.other_findings!.map((o) => o.as_written.toLowerCase()))].join(', ')}.
        </Text>
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
        {d.biobert
          ? `BioBERT found ${d.biobert.drugs_found} drug and ${d.biobert.diseases_found} disease mentions. `
          : ''}
        The note is not de-identified and is shown here only to the underwriter holding the case.
      </Text>
    </div>
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

  if (!d.probabilities) {
    return (
      <Text size="sm" c="dimmed">
        No result was stored.
      </Text>
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
    <div>
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
        Trained on Brazilian tracings; not a diagnosis, and a reported abnormality is a reason to
        obtain the cardiologist's report.
      </Text>
    </div>
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
