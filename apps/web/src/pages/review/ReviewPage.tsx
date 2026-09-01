import {
  Alert,
  Badge,
  Box,
  Button,
  Divider,
  Group,
  NumberInput,
  Paper,
  SimpleGrid,
  Stack,
  Switch,
  Text,
} from '@mantine/core'
import { IconChevronDown, IconCircleCheck } from '@tabler/icons-react'
import { useState } from 'react'

import {
  TierBadge,
  type Tier,
} from '../../components/TierBadge'

/**
 * Review workspace — the underwriter, alone, 1–2 days later.
 *
 * Answers one question: should I trust this recommendation, and what do I
 * decide? Evidence on the left, reasoning and decision on the right.
 *
 * Decision invariants:
 *  · NO reject button — escalation is the path.
 *  · Decision is write-once: the panel becomes read-only after submission.
 *  · `approved_with_adjustment` reveals a final-premium input.
 *
 * TODO: fetch `GET /api/applications/:id` (score, findings, explanation
 * artifacts, model runs), `GET /api/files/:id` for the X-ray + heatmap, and
 * `POST /api/applications/:id/decision`. Handle "not scored yet", "scoring
 * failed", "no heatmap", and "already decided" states.
 */

type DecisionType =
  | 'confirmed_fast_track'
  | 'approved_with_adjustment'
  | 'escalated_senior_review'
  | 'requested_additional_evidence'

const DECISIONS: { value: DecisionType; label: string }[] = [
  { value: 'confirmed_fast_track', label: 'Confirm fast-track' },
  { value: 'approved_with_adjustment', label: 'Approve with adjustment' },
  { value: 'escalated_senior_review', label: 'Escalate to senior underwriter' },
  { value: 'requested_additional_evidence', label: 'Request more evidence' },
]

/**
 * What the vision arm returns for each of its 18 findings.
 *
 * `probability` is the backbone model's raw output. `contribution` is how much
 * that finding actually moved the TB score, from `details.contributions`.
 *
 * The panel ranks by contribution, not probability, because they disagree: the
 * scorer weights Lung Lesion at +1.509 and Cardiomegaly at +0.018, so a film
 * with high Cardiomegaly and modest Lung Lesion would put Cardiomegaly at the
 * top of a probability list while it moved the decision almost not at all —
 * telling the underwriter the wrong reason for the score.
 */
interface Finding {
  label: string
  probability: number
  contribution: number
}

// Stub — replace with details.findings + details.contributions from the API.
// All 18 labels, spelled as the model emits them (see tb_xray_model.json).
const FINDINGS: Finding[] = [
  { label: 'Lung Lesion', probability: 0.71, contribution: 0.94 },
  { label: 'Nodule', probability: 0.63, contribution: 0.48 },
  { label: 'Pneumothorax', probability: 0.29, contribution: 0.31 },
  { label: 'Infiltration', probability: 0.55, contribution: 0.12 },
  { label: 'Consolidation', probability: 0.41, contribution: 0.09 },
  { label: 'Effusion', probability: 0.24, contribution: 0.07 },
  { label: 'Pleural_Thickening', probability: 0.19, contribution: 0.05 },
  { label: 'Pneumonia', probability: 0.14, contribution: 0.04 },
  { label: 'Fracture', probability: 0.08, contribution: 0.03 },
  { label: 'Hernia', probability: 0.03, contribution: 0.01 },
  { label: 'Cardiomegaly', probability: 0.44, contribution: 0.0 },
  { label: 'Mass', probability: 0.12, contribution: -0.01 },
  { label: 'Emphysema', probability: 0.09, contribution: -0.02 },
  { label: 'Edema', probability: 0.11, contribution: -0.04 },
  { label: 'Enlarged Cardiomediastinum', probability: 0.21, contribution: -0.08 },
  { label: 'Lung Opacity', probability: 0.38, contribution: -0.11 },
  { label: 'Fibrosis', probability: 0.27, contribution: -0.18 },
  { label: 'Atelectasis', probability: 0.33, contribution: -0.52 },
]

const TOP_N = 5

/** `Pleural_Thickening` is the model's own spelling; show it readably. */
function prettyLabel(label: string): string {
  return label.replace(/_/g, ' ')
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
      <Box h={6} w="100%" style={{ backgroundColor: 'var(--mantine-color-dark-5)', borderRadius: 3 }}>
        <Box
          h="100%"
          style={{
            width: `${Math.min(width, 100)}%`,
            backgroundColor: toward
              ? 'var(--mantine-color-clinical-5)'
              : 'var(--mantine-color-dark-3)',
            borderRadius: 3,
          }}
        />
      </Box>
    </div>
  )
}

export function ReviewPage() {
  const [showHeatmap, setShowHeatmap] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [decision, setDecision] = useState<DecisionType | null>(null)
  const [premium, setPremium] = useState<number | undefined>(undefined)
  const [submitting, setSubmitting] = useState(false)
  const [decidedAt, setDecidedAt] = useState<string | null>(null)

  // Scaffolding — replace with data from the API.
  const tier: Tier = 'moderate'
  const scorer = 'logistic_regression_on_txrv_findings v1.0.0 trained on shenzhen'
  const validation = 'Internal 5-fold cross-validation; NOT externally validated'
  const cvAuc = 0.8766
  const evaluatedAt = '2 days ago, 14:02'
  const heatmapAvailable = false
  const decided = decidedAt !== null

  // Ranked by absolute contribution: the findings that moved the score most,
  // in either direction.
  const ranked = [...FINDINGS].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
  const findings = showAll ? ranked : ranked.slice(0, TOP_N)
  const scale = Math.max(...ranked.map((f) => Math.abs(f.contribution)), 0.01)
  const decisionLabel = DECISIONS.find((d) => d.value === decision)?.label ?? ''

  const submit = () => {
    if (!decision) return
    setSubmitting(true)
    // TODO: POST /api/applications/:id/decision (write-once server-side).
    window.setTimeout(() => {
      setSubmitting(false)
      setDecidedAt('just now')
    }, 900)
  }

  return (
    <Stack gap="md">
      {/* ── Header ─────────────────────────────────────────── */}
      <Paper p="sm" bd="1px solid var(--mantine-color-default-border)">
        <Group justify="space-between" wrap="wrap" gap="md">
          <Group gap="md">
            <div className="hl-kv">
              <span className="hl-kv-label">Reference</span>
              <span className="hl-kv-value hl-mono">ABC-12345</span>
            </div>
            <Divider orientation="vertical" />
            <div className="hl-kv">
              <span className="hl-kv-label">Status</span>
              <Badge color="teal" variant="light" size="sm">
                Ready for review
              </Badge>
            </div>
            <Divider orientation="vertical" />
            <div className="hl-kv">
              <span className="hl-kv-label">Applicant</span>
              <span className="hl-kv-value">A. Rahman</span>
            </div>
            <div className="hl-kv">
              <span className="hl-kv-label">Submitted</span>
              <span className="hl-kv-value">2 days ago</span>
            </div>
          </Group>
          <Group gap="sm">
            <div className="hl-kv" style={{ alignItems: 'flex-end' }}>
              <span className="hl-kv-label">CRS</span>
              <span className="hl-kv-value" style={{ fontSize: '1.1rem' }}>
                51.4
              </span>
            </div>
            <TierBadge tier={tier} />
          </Group>
        </Group>
      </Paper>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        {/* ── Left · the image ──────────────────────────────── */}
        <Paper p="sm" bd="1px solid var(--mantine-color-default-border)">
          <Group justify="space-between" mb="sm">
            <Text fw={600} size="sm">
              Chest X-ray
            </Text>
            <Switch
              label="Grad-CAM overlay"
              size="xs"
              checked={showHeatmap}
              onChange={() => setShowHeatmap((v) => !v)}
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
            }}
          >
            <Text c="dimmed" size="sm">
              X-ray placeholder
            </Text>
          </Box>
          {!heatmapAvailable && (
            <Text size="xs" c="dimmed" mt="sm">
              No heatmap produced for this image.
            </Text>
          )}
        </Paper>

        {/* ── Right · why this score ────────────────────────── */}
        <Stack gap="md">
          <Paper p="sm" bd="1px solid var(--mantine-color-default-border)">
            <Group justify="space-between" mb="sm">
              <Text fw={600} size="sm">
                What moved the score
              </Text>
              <Text size="xs" c="dimmed">
                {findings.length} of {FINDINGS.length} shown
              </Text>
            </Group>
            <Stack gap="sm">
              {findings.map((f) => (
                <FindingBar key={f.label} finding={f} scale={scale} />
              ))}
            </Stack>
            <Button
              variant="subtle"
              size="xs"
              mt="sm"
              fullWidth
              rightSection={<IconChevronDown size={14} />}
              onClick={() => setShowAll((v) => !v)}
            >
              {showAll ? `Show top ${TOP_N}` : `Show all ${FINDINGS.length}`}
            </Button>
          </Paper>

          <Paper p="sm" bd="1px solid var(--mantine-color-default-border)">
            <Text fw={600} size="sm" mb="sm">
              What the declared history changed
            </Text>
            <Stack gap={4}>
              <Text size="sm" c="dimmed">
                Previously treated TB, course completed, no current symptoms →
                lowered
              </Text>
            </Stack>
          </Paper>

          {/*
            From details.scorer / details.validation / details.cv_auc. The
            validation string is not decoration: the model has only ever been
            tested on one hospital, and that caveat has to travel with the score
            rather than live in a document.
          */}
          <Stack gap={2}>
            <Text size="xs" c="dimmed">
              {scorer} · evaluated {evaluatedAt}
            </Text>
            <Text size="xs" c="yellow.7">
              {validation} (AUC {cvAuc.toFixed(3)})
            </Text>
          </Stack>
        </Stack>
      </SimpleGrid>

      {/* ── Decision ────────────────────────────────────────── */}
      <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
        <Group justify="space-between" mb="sm">
          <Text fw={600} size="sm">
            Decision
          </Text>
        </Group>

        {decided ? (
          <Alert
            icon={<IconCircleCheck size={18} />}
            color="teal"
            variant="light"
            title="Decision recorded"
          >
            <Text size="sm">
              You marked this as <strong>{decisionLabel}</strong> {decidedAt}.
              Decisions are write-once and can no longer be edited.
            </Text>
          </Alert>
        ) : (
          <>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
              {DECISIONS.map((d) => (
                <Button
                  key={d.value}
                  variant={decision === d.value ? 'filled' : 'light'}
                  color={decision === d.value ? 'clinical' : 'gray'}
                  justify="space-between"
                  onClick={() => setDecision(d.value)}
                >
                  {d.label}
                </Button>
              ))}
            </SimpleGrid>

            {decision === 'approved_with_adjustment' && (
              <NumberInput
                mt="md"
                label="Final premium (BDT)"
                placeholder="1,000,000"
                thousandSeparator=","
                min={0}
                value={premium}
                onChange={(v) => setPremium(typeof v === 'number' ? v : Number(v) || undefined)}
              />
            )}

            <Group justify="space-between" mt="md">
              <Text size="xs" c="dimmed">
                There is no reject button. Escalation to a human underwriter is
                the path.
              </Text>
              <Button
                size="xs"
                disabled={
                  !decision ||
                  // An adjusted approval without a rate is not a decision.
                  (decision === 'approved_with_adjustment' && (premium ?? 0) <= 0)
                }
                onClick={submit}
                loading={submitting}
              >
                Submit decision
              </Button>
            </Group>
          </>
        )}
      </Paper>

      {/* ── Audit trail ─────────────────────────────────────── */}
      <details>
        <summary>
          <Text component="span" size="sm" c="dimmed">
            Audit trail
          </Text>
        </summary>
        <Paper bd="1px solid var(--mantine-color-default-border)" p="sm" mt="sm">
          <Text size="sm" c="dimmed">
            TODO: collapsed, expandable table of timestamp / event / actor from
            `GET /api/applications/:id/audit`.
          </Text>
        </Paper>
      </details>
    </Stack>
  )
}
