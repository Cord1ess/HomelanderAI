import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Divider,
  Group,
  NumberInput,
  Paper,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  Title,
} from '@mantine/core'
import { useState } from 'react'

/**
 * Review workspace — the underwriter, alone, 1–2 days later.
 *
 * Answers one question: should I trust this recommendation, and what do I
 * decide? Evidence on the left, reasoning and decision on the right.
 *
 * TODO: fetch `GET /api/applications/:id` (score, findings, explanation
 * artifacts, model runs), `GET /api/files/:id` for the X-ray + heatmap, and
 * `POST /api/applications/:id/decision`. Handle "not scored yet", "scoring
 * failed", "no heatmap", and "already decided" states.
 */

type Tier = 'low' | 'moderate' | 'elevated' | 'insufficient' | null

const TIER_META: Record<NonNullable<Tier>, { label: string; color: string }> = {
  low: { label: 'Low', color: 'teal' },
  moderate: { label: 'Moderate', color: 'yellow' },
  elevated: { label: 'Elevated', color: 'red' },
  insufficient: { label: 'Insufficient evidence', color: 'gray' },
}

type DecisionType =
  | 'confirmed_fast_track'
  | 'approved_with_adjustment'
  | 'escalated_senior_review'
  | 'requested_additional_evidence'

const DECISIONS: { label: string; value: DecisionType }[] = [
  { label: 'Confirm fast-track', value: 'confirmed_fast_track' },
  { label: 'Approve with adjustment', value: 'approved_with_adjustment' },
  { label: 'Escalate to senior underwriter', value: 'escalated_senior_review' },
  { label: 'Request more evidence', value: 'requested_additional_evidence' },
]

const FINDINGS = [
  { label: 'Opacity', value: 0.92 },
  { label: 'Effusion', value: 0.61 },
  { label: 'Nodule', value: 0.47 },
  { label: 'Cardiomegaly', value: 0.33 },
  { label: 'Fibrosis', value: 0.21 },
] // TODO: from sub_scores; "top 5" + "Show all 18"

export function ReviewPage() {
  const [showHeatmap, setShowHeatmap] = useState(false)
  const [decision, setDecision] = useState<DecisionType | null>(null)

  // Scaffolding — replace with data from the API.
  const tier: Tier = 'low'
  const decided = false
  const heatmapAvailable = false

  return (
    <Container size="xl">
      <Stack gap="md">
        {/* ── Header ─────────────────────────────────────────── */}
        <Group justify="space-between" wrap="wrap">
          <Stack gap={2}>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: '0.12em' }}>
              Application
            </Text>
            <Group gap="sm">
              <Title order={1} ff="monospace">
                ABC-12345
              </Title>
              <Badge color="teal">Ready for review</Badge>
            </Group>
            <Text size="sm" c="dimmed">
              Submitted 2 days ago
            </Text>
          </Stack>

          <Group gap="sm">
            <Text size="sm" c="dimmed">
              CRS
            </Text>
            <Text size="xl" fw={700}>
              3.2
            </Text>
            {tier ? <Badge color={TIER_META[tier].color}>{TIER_META[tier].label}</Badge> : null}
          </Group>
        </Group>

        <Divider />

        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
          {/* ── Left · the image ──────────────────────────────── */}
          <Stack gap="md">
            <Card>
              <Group justify="space-between" mb="sm">
                <Text fw={600} size="sm">
                  Chest X-ray
                </Text>
                <Switch
                  label="Grad-CAM overlay"
                  checked={showHeatmap}
                  onChange={() => setShowHeatmap((v) => !v)}
                  disabled={!heatmapAvailable}
                />
              </Group>

              {/* TODO: <img src={`/api/files/:id`} /> of the X-ray (plus heatmap PNG
                  overlay when the toggle is on). No DICOM viewer in Phase 1. */}
              <Box
                h={320}
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
            </Card>
          </Stack>

          {/* ── Right · why this score ────────────────────────── */}
          <Stack gap="md">
            <Card>
              <Text fw={600} size="sm" mb="sm">
                Findings
              </Text>
              <Stack gap="sm">
                {FINDINGS.map((f) => (
                  <div key={f.label}>
                    <Group justify="space-between" mb={4}>
                      <Text size="xs">{f.label}</Text>
                      <Text size="xs" ff="monospace">
                        {f.value.toFixed(2)}
                      </Text>
                    </Group>
                    <Box
                      h={6}
                      w="100%"
                      style={{ backgroundColor: 'var(--mantine-color-dark-5)', borderRadius: 3 }}
                    >
                      <Box
                        h="100%"
                        style={{
                          width: `${f.value * 100}%`,
                          backgroundColor: 'var(--mantine-color-clinical-5)',
                          borderRadius: 3,
                        }}
                      />
                    </Box>
                  </div>
                ))}
              </Stack>
              <Button variant="subtle" size="xs" mt="sm" fullWidth>
                Show all 18
              </Button>
            </Card>

            <Card>
              <Text fw={600} size="sm" mb="sm">
                What the declared history changed
              </Text>
              <Stack gap={4}>
                <Text size="sm" c="dimmed">
                  Previously treated TB, course completed, no current symptoms →
                  lowered
                </Text>
              </Stack>
            </Card>

            <Text size="xs" c="dimmed">
              Model: torxray-v1 · v1.0.3 · evaluated 2 days ago, 14:02
            </Text>
          </Stack>
        </SimpleGrid>

        {/* ── Decision ────────────────────────────────────────── */}
        {decided ? (
          <Card>
            <Text fw={600} size="sm">
              Decided
            </Text>
            <Text size="sm" c="dimmed">
              <Text component="span">Operator</Text> marked this as{' '}
              <strong>Confirm fast-track</strong> on 2 days ago, 15:00. Decision
              is write-once and can no longer be edited.
            </Text>
          </Card>
        ) : (
          <Card>
            <Text fw={600} size="sm" mb="sm">
              Decision
            </Text>
            {tier === null && (
              <Alert color="gray" variant="light" mb="sm">
                <Text size="sm">Not scored yet — evaluation pending. No decision can be made yet.</Text>
              </Alert>
            )}
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              {DECISIONS.map((d) => (
                <Button
                  key={d.value}
                  variant={decision === d.value ? 'filled' : 'light'}
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
              />
            )}
            <Text size="xs" c="dimmed" mt="sm">
              There is no reject button. Escalation to a human underwriter is the
              path.
            </Text>
          </Card>
        )}

        {/* ── Audit trail ─────────────────────────────────────── */}
        <Details summary="Audit trail">
          <Text size="sm" c="dimmed">
            TODO: collapsed, expandable table of timestamp / event / actor from
            `GET /api/applications/:id/audit`.
          </Text>
        </Details>
      </Stack>
    </Container>
  )
}

function Details({ summary, children }: { summary: string; children: React.ReactNode }) {
  return (
    <details>
      <summary>
        <Text component="span" size="sm" c="dimmed">
          {summary}
        </Text>
      </summary>
      <Paper withBorder p="md" mt="sm">
        {children}
      </Paper>
    </details>
  )
}
