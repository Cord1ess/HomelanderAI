import { BarChart, DonutChart } from '@mantine/charts'
import { Card, Group, SimpleGrid, Stack, Table, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'

import { getAnalytics } from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { Stat } from '../../components/Stat'
import { EmptyState, ErrorState, LoadingState } from '../../components/states'
import { TIER_META, type Tier } from '../../components/TierBadge'
import { STATUS_META } from '../../status'

/**
 * Analytics: the company's book in numbers. Every figure is computed by the
 * API from real applications; there is nothing here a row does not back.
 */

const BDT = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const taka = (v: string | number) => `৳${BDT.format(Number(v))}`

const DECISION_LABEL: Record<string, string> = {
  confirmed_fast_track: 'Standard rate',
  approved_with_adjustment: 'Adjusted premium',
  escalated_senior_review: 'Escalated (old records)',
  requested_additional_evidence: 'Evidence requested (old records)',
}

const ARM_LABEL: Record<string, string> = {
  tb_xray: 'Chest X-ray',
  dr_fundus: 'Retinal photo',
  ecg_12lead: '12-lead ECG',
  mortality: 'Blood panel',
}

const TIER_COLOR: Record<string, string> = {
  low: 'teal.6',
  moderate: 'yellow.6',
  elevated: 'red.6',
  insufficient_evidence: 'gray.5',
}

function Panel({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <Card p="md">
      <Text fw={600} size="sm">{title}</Text>
      {hint && (
        <Text size="xs" mb="sm" style={{ color: 'var(--neo-muted)' }}>{hint}</Text>
      )}
      {children}
    </Card>
  )
}

export function AnalyticsPage() {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['analytics'],
    queryFn: getAnalytics,
    refetchInterval: 60_000,
  })

  if (isPending) {
    return (
      <Stack gap="md">
        <PageHeader screen="analytics" />
        <LoadingState label="Adding up the book" />
      </Stack>
    )
  }
  if (error || !data) {
    return (
      <Stack gap="md">
        <PageHeader screen="analytics" />
        <ErrorState title="Could not load the analytics" error={error} retry={() => void refetch()} />
      </Stack>
    )
  }

  if (data.applications === 0) {
    return (
      <Stack gap="md">
        <PageHeader screen="analytics" />
        <EmptyState title="Nothing to count yet" text="Take the first application and the figures appear here." />
      </Stack>
    )
  }

  const approvalRate = data.decided ? Math.round((data.approved / data.decided) * 100) : null
  // Lists are optional in the generated type because the API gives them defaults.
  const tiers = (data.byTier ?? []).map((t) => ({
    name: TIER_META[t.key as Tier]?.label ?? t.key,
    value: t.count,
    color: TIER_COLOR[t.key] ?? 'gray.5',
  }))
  const statuses = (data.byStatus ?? []).map((s) => ({
    status: STATUS_META[s.key as keyof typeof STATUS_META]?.label ?? s.key,
    Applications: s.count,
  }))
  const decisions = (data.byDecision ?? []).map((d) => ({
    decision: DECISION_LABEL[d.key] ?? d.key,
    Decisions: d.count,
  }))
  const weeks = (data.weeks ?? []).map((w) => ({
    week: new Date(`${w.weekOf}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }),
    Taken: w.applications,
    Decided: w.decided,
  }))

  return (
    <Stack gap="md">
      <PageHeader screen="analytics">
        <SimpleGrid cols={{ base: 2, md: 3, lg: 6 }} spacing="xs">
          <Stat label="Applications" value={data.applications} />
          <Stat label="Waiting" value={data.waiting} color="orange" hint={data.escalated ? `${data.escalated} with a medical professional` : undefined} />
          <Stat label="Decided" value={data.decided} color="teal" hint={approvalRate != null ? `${approvalRate}% approved` : undefined} />
          <Stat label="Average score" value={data.averageCrs ?? '—'} hint="Across scored applications" />
          <Stat label="Cover requested" value={taka(data.coverRequestedBdt)} hint={`${taka(data.coverApprovedBdt)} approved`} />
          <Stat label="Monthly premium book" value={taka(data.monthlyPremiumBookBdt)} color="clinical" hint="Sum of approved premiums" />
        </SimpleGrid>
      </PageHeader>

      <SimpleGrid cols={{ base: 1, lg: 3 }} spacing="md">
        <Panel title="Risk tiers" hint="Latest score per application">
          {tiers.length ? (
            <Group justify="center">
              <DonutChart data={tiers} size={150} thickness={22} withLabelsLine={false} withLabels chartLabel={`${data.applications}`} />
            </Group>
          ) : (
            <Text size="sm" c="dimmed">No scores yet.</Text>
          )}
        </Panel>
        <Panel title="Where applications are" hint="By status, right now">
          <BarChart h={180} data={statuses} dataKey="status" series={[{ name: 'Applications', color: 'clinical.6' }]} orientation="vertical" withLegend={false} gridAxis="none" />
        </Panel>
        <Panel title="Decisions" hint="What was recorded">
          {decisions.length ? (
            <BarChart h={180} data={decisions} dataKey="decision" series={[{ name: 'Decisions', color: 'teal.6' }]} orientation="vertical" withLegend={false} gridAxis="none" />
          ) : (
            <Text size="sm" c="dimmed">No decisions yet.</Text>
          )}
        </Panel>
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        <Panel title="Applications per week" hint="The last eight weeks">
          <BarChart h={200} data={weeks} dataKey="week" series={[{ name: 'Taken', color: 'clinical.6' }, { name: 'Decided', color: 'teal.6' }]} withLegend gridAxis="y" />
        </Panel>
        <Panel title="Turnaround" hint="Against the date promised to the client">
          <SimpleGrid cols={3} spacing="xs">
            <Stat label="Days to decide" value={data.averageDaysToDecide ?? '—'} hint="Average, submit to decision" />
            <Stat label="On time" value={data.decidedOnTime} color="teal" />
            <Stat label="Late" value={data.decidedLate} color={data.decidedLate ? 'red' : undefined} />
          </SimpleGrid>
        </Panel>
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        <Panel title="By cover type" hint="What clients ask for">
          <Table fz="sm" withRowBorders={false} verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Cover</Table.Th>
                <Table.Th>Applications</Table.Th>
                <Table.Th>Approved</Table.Th>
                <Table.Th>Amount requested</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(data.byCoverType ?? []).map((c) => (
                <Table.Tr key={c.coverageType}>
                  <Table.Td tt="capitalize">{c.coverageType.replace(/_/g, ' ')}</Table.Td>
                  <Table.Td>{c.count}</Table.Td>
                  <Table.Td>{c.approved}</Table.Td>
                  <Table.Td ff="monospace">{taka(c.amountBdt)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Panel>
        <Panel title="Readers" hint="How often each ran, what it scored on average, and how often it failed">
          <Table fz="sm" withRowBorders={false} verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Reader</Table.Th>
                <Table.Th>Runs</Table.Th>
                <Table.Th>Average score</Table.Th>
                <Table.Th>Failed</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(data.arms ?? []).map((a) => (
                <Table.Tr key={a.arm}>
                  <Table.Td>{ARM_LABEL[a.arm] ?? a.arm}</Table.Td>
                  <Table.Td>{a.runs}</Table.Td>
                  <Table.Td ff="monospace">{a.averageScore ?? '—'}</Table.Td>
                  <Table.Td style={{ color: a.failed ? 'var(--neo-danger)' : undefined }}>{a.failed}</Table.Td>
                </Table.Tr>
              ))}
              {(data.arms ?? []).length === 0 && (
                <Table.Tr><Table.Td colSpan={4}><Text size="sm" c="dimmed">No reader has run yet.</Text></Table.Td></Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Panel>
      </SimpleGrid>
    </Stack>
  )
}
