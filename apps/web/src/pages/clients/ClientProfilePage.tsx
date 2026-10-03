import { Anchor, Badge, Box, Button, Grid, Group, Paper, SimpleGrid, Stack, Table, Text } from '@mantine/core'
import { IconArrowRight } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError, getApplication, getClient } from '../../api/client'
import { DoctorVerdictBadge } from '../../components/DoctorVerdictBadge'
import { PageHeader } from '../../components/PageHeader'
import { ErrorState, LoadingState } from '../../components/states'
import { StatusBadge } from '../../components/StatusBadge'
import { TierBadge, type Tier } from '../../components/TierBadge'
import { ReaderCards } from '../review/ReaderCards'
import { groupRuns, limitsOf } from '../review/readers'
import { PolicyPanel } from './PolicyPanel'
import { RequestAccessForm } from './RequestAccess'

/**
 * One client: who they are, what they applied for, and what their tests said.
 *
 * The list of clients is for finding someone; this is what opening them shows.
 * The readers' results are the same cards as on the result page, and each one
 * opens the result page on that reader.
 */

const DECISION_LABELS: Record<string, string> = {
  confirmed_fast_track: 'Approved at the standard rate',
  approved_with_adjustment: 'Approved with an adjusted premium',
  escalated_senior_review: 'Sent to a doctor',
}

const taka = (value: string | number) => `৳${Math.round(Number(value)).toLocaleString('en-IN')}`

const day = (iso: string) =>
  new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })

function ageOn(dateOfBirth: string, when = new Date()): number {
  const born = new Date(`${dateOfBirth}T00:00:00`)
  let age = when.getFullYear() - born.getFullYear()
  const m = when.getMonth() - born.getMonth()
  if (m < 0 || (m === 0 && when.getDate() < born.getDate())) age -= 1
  return age
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

export function ClientProfilePage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const client = useQuery({
    queryKey: ['client', id],
    queryFn: () => getClient(id!),
    enabled: Boolean(id),
    // A refusal is an answer, not a hiccup: asking again will not change it.
    retry: (count, e) => !(e instanceof ApiError && (e.status === 403 || e.status === 404)) && count < 2,
  })
  const latestId = client.data?.applications?.[0]?.id
  const latest = useQuery({
    queryKey: ['application', latestId],
    queryFn: () => getApplication(latestId!),
    enabled: Boolean(latestId),
  })

  if (client.isPending) return <LoadingState label="Loading the client" />
  if (client.error instanceof ApiError && client.error.status === 403 && id) {
    return (
      <Stack gap="md" maw={640}>
        <PageHeader
          screen="client"
          title="Client details are hidden"
          actions={
            <Anchor component={Link} to="/clients" size="sm">
              All clients
            </Anchor>
          }
        />
        <Paper p="lg" bd="1px solid var(--mantine-color-default-border)">
          <RequestAccessForm clientId={id} reference="this client" />
        </Paper>
      </Stack>
    )
  }
  if (client.error || !client.data) {
    return <ErrorState title="Could not load this client" error={client.error} retry={() => void client.refetch()} />
  }

  const c = client.data
  const apps = c.applications ?? []
  const height = c.heightCm != null ? Number(c.heightCm) : null
  const weight = c.weightKg != null ? Number(c.weightKg) : null
  const bmi = height && weight ? weight / (height / 100) ** 2 : null
  const detail = latest.data
  const groups = detail ? groupRuns(detail.arms ?? []) : []

  return (
    <Stack gap="md">
      <PageHeader
        screen="client"
        title={
          <span>
            {c.name ?? 'Client'} <span className="hl-mono">{c.reference}</span>
          </span>
        }
        actions={
          <Anchor component={Link} to="/clients" size="sm">
            All clients
          </Anchor>
        }
      />

      {(c.policies ?? []).length > 0 && <PolicyPanel policies={c.policies ?? []} clientId={c.id} />}

      <Grid gap="md" align="flex-start">
        {/* ── Who they are ─────────────────────────────────────── */}
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
            <Text fw={600} size="sm" mb="sm">
              Client details
            </Text>
            <SimpleGrid cols={2} spacing="md">
              <Field label="Reference">
                <span className="hl-mono">{c.reference}</span>
              </Field>
              <Field label="Portal ID">
                <span className="hl-mono">{c.portalId ?? '—'}</span>
              </Field>
              <Field label="Date of birth">
                {c.dateOfBirth ? (
                  <>
                    {day(c.dateOfBirth)}
                    <Text span c="dimmed" fw={400}>
                      {' '}
                      · {ageOn(c.dateOfBirth)}
                    </Text>
                  </>
                ) : (
                  '—'
                )}
              </Field>
              <Field label="Sex">{c.sex ?? '—'}</Field>
              <Field label="Phone">{c.phone ?? '—'}</Field>
              <Field label="Email">
                <Text span size="sm" fw={600} style={{ wordBreak: 'break-all' }}>
                  {c.email ?? '—'}
                </Text>
              </Field>
              <Field label="Height · weight">
                {height && weight ? `${height} cm · ${weight} kg` : '—'}
              </Field>
              <Field label="BMI">{bmi ? bmi.toFixed(1) : '—'}</Field>
            </SimpleGrid>
            <Text size="xs" c="dimmed" mt="md">
              Client since {day(c.createdAt)}. The portal ID is what they sign in with to see where
              their application stands; they never see a score.
            </Text>
          </Paper>
        </Grid.Col>

        {/* ── What their tests said ─────────────────────────────── */}
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Stack gap="md">
            {apps.length === 0 ? (
              <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
                <Text size="sm" c="dimmed">
                  No application on record for this client.
                </Text>
              </Paper>
            ) : (
              <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
                {(() => {
                  const app = apps[0]
                  return (
                    <>
                      <Group justify="space-between" align="flex-start" mb="md" wrap="wrap" gap="sm">
                        <div>
                          <Text fw={600} size="sm">
                            Latest application
                          </Text>
                          <Text size="xs" c="dimmed">
                            Submitted {day(app.submittedAt)}
                            {app.coverageAmount
                              ? ` · ${taka(app.coverageAmount)}${app.coverageType ? ` ${app.coverageType}` : ''}${app.policyTerm ? `, ${app.policyTerm} yr` : ''}`
                              : ''}
                          </Text>
                        </div>
                        <Group gap="sm" wrap="nowrap">
                          <StatusBadge status={app.status} />
                          {app.crs != null && (
                            <Text fw={700} size="xl" ff="monospace">
                              {app.crs.toFixed(1)}
                            </Text>
                          )}
                          {app.tier && <TierBadge tier={app.tier as Tier} />}
                          <DoctorVerdictBadge verdict={app.doctorVerdict} />
                        </Group>
                      </Group>

                      {app.decision && (
                        <Box
                          mb="md"
                          p="sm"
                          style={{
                            borderRadius: 'var(--mantine-radius-sm)',
                            backgroundColor: 'var(--mantine-color-default-hover)',
                          }}
                        >
                          <Text size="sm">
                            <Text span fw={600}>
                              {DECISION_LABELS[app.decision] ?? app.decision}
                            </Text>
                            {app.decidedAt && (
                              <Text span c="dimmed">
                                {' '}
                                · {day(app.decidedAt)}
                              </Text>
                            )}
                          </Text>
                        </Box>
                      )}

                      {latest.isPending ? (
                        <Text size="sm" c="dimmed">
                          Loading the readings…
                        </Text>
                      ) : groups.length === 0 ? (
                        <Text size="sm" c="dimmed">
                          {app.status === 'submitted' || app.status === 'processing'
                            ? 'The readers are still reading the evidence.'
                            : 'No reader produced a result for this application.'}
                        </Text>
                      ) : (
                        <>
                          <Text size="xs" c="dimmed" mb="xs">
                            What each test found. Select one to open its full result.
                          </Text>
                          <ReaderCards
                            groups={groups}
                            limits={limitsOf(detail!)}
                            onSelect={(arm) => navigate(`/applications/${app.id}?reader=${arm}`)}
                          />
                        </>
                      )}

                      <Group justify="flex-end" mt="md">
                        <Button
                          component={Link}
                          to={`/applications/${app.id}`}
                          size="xs"
                          rightSection={<IconArrowRight size={14} />}
                        >
                          Open the full results
                        </Button>
                      </Group>
                    </>
                  )
                })()}
              </Paper>
            )}

            {apps.length > 1 && (
              <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
                <Text fw={600} size="sm" mb="sm">
                  Every application
                </Text>
                <Table.ScrollContainer minWidth={560}>
                  <Table fz="sm" highlightOnHover>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Submitted</Table.Th>
                        <Table.Th>Status</Table.Th>
                        <Table.Th>Score</Table.Th>
                        <Table.Th>Decision</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {apps.map((a) => (
                        <Table.Tr
                          key={a.id}
                          style={{ cursor: 'pointer' }}
                          onClick={() => navigate(`/applications/${a.id}`)}
                        >
                          <Table.Td>{day(a.submittedAt)}</Table.Td>
                          <Table.Td>
                            <StatusBadge status={a.status} />
                          </Table.Td>
                          <Table.Td>
                            {a.crs != null ? (
                              <Group gap={6} wrap="nowrap">
                                <Text size="sm" ff="monospace">
                                  {a.crs.toFixed(1)}
                                </Text>
                                {a.tier && <TierBadge tier={a.tier as Tier} />}
                                <DoctorVerdictBadge verdict={a.doctorVerdict} size="xs" />
                              </Group>
                            ) : (
                              '—'
                            )}
                          </Table.Td>
                          <Table.Td>
                            {a.decision ? (
                              DECISION_LABELS[a.decision] ?? a.decision
                            ) : (
                              <Badge size="xs" variant="light" color="gray">
                                Open
                              </Badge>
                            )}
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              </Paper>
            )}
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
