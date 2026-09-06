import {
  Alert,
  Badge,
  Card,
  Center,
  Group,
  Loader,
  NumberInput,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
} from '@mantine/core'
import { IconAlertTriangle, IconInfoCircle } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { getPricing } from '../../api/client'
import { TierBadge, type Tier } from '../../components/TierBadge'

/**
 * Pricing — what each risk tier means for the policy.
 *
 * Every number here comes from `GET /api/pricing`. The dashboard deliberately
 * keeps no copy of the rates or the tier cut-points: two copies drift, and a
 * screen quoting a premium against the wrong band is worse than no screen.
 */

const BDT = new Intl.NumberFormat('en-BD', { maximumFractionDigits: 0 })

/** Cover amounts an operator actually types, so the table is useful immediately. */
const PRESETS = [500_000, 1_000_000, 2_500_000, 5_000_000]

export function PricingPage() {
  const [coverage, setCoverage] = useState<number>(1_000_000)

  const { data, isPending, error } = useQuery({
    queryKey: ['pricing', coverage],
    queryFn: () => getPricing(coverage),
    staleTime: 5 * 60 * 1000,
  })

  if (isPending) {
    return (
      <Center mih={240}>
        <Loader color="clinical" type="dots" />
      </Center>
    )
  }

  if (error || !data) {
    return (
      <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} />} title="Could not load pricing">
        {error instanceof Error ? error.message : 'Unknown error'}
      </Alert>
    )
  }

  const band = (tier: string) => {
    if (tier === 'low') return `0 – ${data.lowMax}`
    if (tier === 'moderate') return `${data.lowMax + 0.1} – ${data.moderateMax}`
    if (tier === 'elevated') return `${data.moderateMax + 0.1} – 100`
    return 'no score'
  }

  return (
    <Stack gap="lg" maw={980}>
      <div>
        <Text size="lg" fw={600}>
          Pricing structure
        </Text>
        <Text size="sm" c="dimmed" maw={680}>
          What the platform recommends at each risk tier, and the premium that
          goes with it. Every recommendation still needs an underwriter to
          record the decision — nothing here is issued automatically.
        </Text>
      </div>

      <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
        <Group align="flex-end" gap="md" wrap="wrap">
          <NumberInput
            label="Cover requested"
            description="Premiums below scale with this"
            thousandSeparator=","
            prefix="৳ "
            min={0}
            step={100_000}
            value={coverage}
            onChange={(v) => setCoverage(typeof v === 'number' ? v : Number(v) || 0)}
            w={240}
          />
          <Group gap="xs" pb={4}>
            {PRESETS.map((amount) => (
              <Badge
                key={amount}
                variant={coverage === amount ? 'filled' : 'outline'}
                color={coverage === amount ? 'clinical' : 'gray'}
                style={{ cursor: 'pointer' }}
                onClick={() => setCoverage(amount)}
              >
                ৳{BDT.format(amount)}
              </Badge>
            ))}
          </Group>
        </Group>
      </Paper>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        {data.plans.map((plan) => (
          <Card
            key={plan.tier}
            withBorder
            padding="md"
            bd="1px solid var(--mantine-color-default-border)"
          >
            <Group justify="space-between" mb="xs">
              <TierBadge tier={plan.tier as Tier} />
              <Text size="xs" c="dimmed" ff="monospace">
                score {band(plan.tier)}
              </Text>
            </Group>

            <Text fw={600} size="sm">
              {plan.name}
            </Text>

            <Text size="xl" fw={700} mt={4}>
              {plan.monthlyPremiumBdt != null ? (
                <>
                  ৳{BDT.format(plan.monthlyPremiumBdt)}
                  <Text span size="sm" c="dimmed" fw={400}>
                    {' '}
                    / month
                  </Text>
                </>
              ) : (
                <Text span size="sm" c="dimmed" fw={500}>
                  No rate quoted until a person has looked
                </Text>
              )}
            </Text>

            <Text size="sm" c="dimmed" mt="sm">
              {plan.recommendation}
            </Text>

            <Text size="xs" c="dimmed" mt="xs">
              <Text span fw={600}>
                Human step:
              </Text>{' '}
              {plan.humanStep}
            </Text>

            {plan.wellnessDiscountEligible && (
              <Badge size="xs" variant="light" color="teal" mt="sm">
                Wellness-plan discount eligible
              </Badge>
            )}
          </Card>
        ))}
      </SimpleGrid>

      <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
        <Text fw={600} size="sm" mb="sm">
          At a glance
        </Text>
        <Table.ScrollContainer minWidth={620}>
          <Table fz="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Tier</Table.Th>
                <Table.Th>Score</Table.Th>
                <Table.Th>Plan</Table.Th>
                <Table.Th>Monthly premium</Table.Th>
                <Table.Th>Who signs it off</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.plans.map((plan) => (
                <Table.Tr key={plan.tier}>
                  <Table.Td>
                    <TierBadge tier={plan.tier as Tier} />
                  </Table.Td>
                  <Table.Td ff="monospace" c="dimmed">
                    {band(plan.tier)}
                  </Table.Td>
                  <Table.Td>{plan.name}</Table.Td>
                  <Table.Td ff="monospace">
                    {plan.monthlyPremiumBdt != null
                      ? `৳${BDT.format(plan.monthlyPremiumBdt)}`
                      : '—'}
                  </Table.Td>
                  <Table.Td c="dimmed">{plan.humanStep}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Paper>

      {/*
        Saying this on the screen rather than only in a document. Idea.md gives a
        premium per tier and no rate card, so the scaling is an assumption, and
        anyone reading a number off this page should know that.
      */}
      <Alert color="yellow" variant="light" icon={<IconInfoCircle size={18} />} title="How these numbers are worked out">
        <Text size="sm">
          Each tier has a baseline monthly premium at a reference cover of{' '}
          <Text span fw={600}>
            ৳{BDT.format(data.plans[0]?.referenceCoverBdt ?? 1_000_000)}
          </Text>
          , and the figures above scale linearly from it — asking for twice the
          cover doubles the premium.
        </Text>
        <Text size="sm" mt="xs">
          These are illustrative rates taken from the project specification, not
          actuarial pricing. There is no mortality table, no expense loading and
          no reinsurance behind them. Elevated risk carries no quoted rate on
          purpose: attaching a price to it would imply an outcome that has not
          been decided, and it is never an automated denial.
        </Text>
      </Alert>
    </Stack>
  )
}
