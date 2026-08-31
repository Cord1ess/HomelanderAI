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

const FINDINGS_TOP = [
  { label: 'Opacity', value: 0.92 },
  { label: 'Effusion', value: 0.61 },
  { label: 'Nodule', value: 0.47 },
  { label: 'Cardiomegaly', value: 0.33 },
  { label: 'Fibrosis', value: 0.21 },
]

const FINDINGS_REST = [
  { label: 'Atelectasis', value: 0.14 },
  { label: 'Pneumothorax', value: 0.11 },
  { label: 'Consolidation', value: 0.09 },
  { label: 'Edema', value: 0.07 },
  { label: 'Emphysema', value: 0.05 },
  { label: 'Mass', value: 0.04 },
  { label: 'Pleural thickening', value: 0.03 },
  { label: 'Hernia', value: 0.02 },
]

function FindingBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <Group justify="space-between" mb={4}>
        <Text size="xs">{label}</Text>
        <Text size="xs" ff="monospace" c="dimmed">
          {(value * 100).toFixed(0)}%
        </Text>
      </Group>
      <Box h={6} w="100%" style={{ backgroundColor: 'var(--mantine-color-dark-5)', borderRadius: 3 }}>
        <Box
          h="100%"
          style={{
            width: `${Math.min(value * 100, 100)}%`,
            backgroundColor: 'var(--mantine-color-clinical-5)',
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
  const tier: Tier = 'low'
  const heatmapAvailable = false
  const decided = decidedAt !== null

  const findings = showAll ? [...FINDINGS_TOP, ...FINDINGS_REST] : FINDINGS_TOP
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
                3.2
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
                Findings
              </Text>
              <Text size="xs" c="dimmed">
                {showAll ? FINDINGS_TOP.length + FINDINGS_REST.length : FINDINGS_TOP.length} shown
              </Text>
            </Group>
            <Stack gap="sm">
              {findings.map((f) => (
                <FindingBar key={f.label} label={f.label} value={f.value} />
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
              {showAll ? 'Show top 5' : `Show all ${FINDINGS_TOP.length + FINDINGS_REST.length}`}
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

          <Text size="xs" c="dimmed">
            Model: torxray-v1 · v1.0.3 · evaluated 2 days ago, 14:02
          </Text>
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
              <Button size="xs" disabled={!decision} onClick={submit} loading={submitting}>
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
