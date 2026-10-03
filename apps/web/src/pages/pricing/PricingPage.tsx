import {
  Alert,
  Badge,
  Card,
  Checkbox,
  Group,
  NumberInput,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
} from '@mantine/core'
import { IconInfoCircle } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { getPricing, quote } from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { ErrorState, LoadingState } from '../../components/states'
import { PricingPolicyCard } from '../admin/PricingPolicyCard'

const taka = (v: string | number) => `৳${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
const lakh = (v: number) => (v >= 10_000_000 ? `${v / 10_000_000} crore` : `${v / 100_000} lakh`)

/**
 * Plans and pricing: the two products, what they cost, and the assumptions
 * behind it. Every figure comes from the pricing engine on the server; the
 * dashboard keeps no rate of its own.
 */
export function PricingPage() {
  const { data, isPending, error, refetch } = useQuery({ queryKey: ['pricing'], queryFn: getPricing })

  if (isPending) {
    return (
      <Stack gap="lg" maw={1080}>
        <PageHeader screen="pricing" />
        <LoadingState label="Working out the prices" />
      </Stack>
    )
  }
  if (error || !data) {
    return (
      <Stack gap="lg" maw={1080}>
        <PageHeader screen="pricing" />
        <ErrorState title="Could not load the prices" error={error} retry={() => void refetch()} />
      </Stack>
    )
  }

  const examples = data.examples ?? []
  return (
    <Stack gap="lg" maw={1080}>
      <PageHeader screen="pricing" />

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        <Card p="md">
          <Group justify="space-between">
            <Text fw={700}>Term life</Text>
            <Badge variant="light">Level premium</Badge>
          </Group>
          <Text size="sm" mt={4}>
            Pays the sum assured to the nominee if the client dies during the term. The premium stays the same every year.
          </Text>
          <Stack gap={2} mt="sm">
            <Text size="xs">Sums assured: {data.lifeAmounts.map((a) => lakh(a)).join(', ')}</Text>
            <Text size="xs">Terms: {data.lifeTerms.join(', ')} years</Text>
            <Text size="xs">
              Ages {data.lifeEntryAges[0]} to {data.lifeEntryAges[1]} at the start; cover ends by {data.lifeMaxExpiryAge}
            </Text>
            <Text size="xs">Free look: {data.freeLookDays} days to cancel for a full refund</Text>
          </Stack>
        </Card>
        <Card p="md">
          <Group justify="space-between">
            <Text fw={700}>Hospital cover</Text>
            <Badge variant="light" color="grape">
              One year, renewed yearly
            </Badge>
          </Group>
          <Text size="sm" mt={4}>
            Pays hospital and treatment bills up to the yearly limit. Renewed each year at the client's new age.
          </Text>
          <Stack gap={2} mt="sm">
            <Text size="xs">Yearly limits: {data.healthAmounts.map((a) => lakh(a)).join(', ')}</Text>
            <Text size="xs">
              Ages {data.healthEntryAges[0]} to {data.healthEntryAges[1]} at the start
            </Text>
            <Text size="xs">
              Waiting: illness {data.healthIllnessWaitDays} days (accidents none), conditions already had{' '}
              {data.healthPreexistingWaitMonths} months
            </Text>
            <Text size="xs">Findings and declared conditions can be excluded at approval</Text>
          </Stack>
        </Card>
      </SimpleGrid>

      <Alert variant="light" color="clinical" icon={<IconInfoCircle size={16} />}>
        <Text size="sm">
          A moderate reading is approved at a rating and, for hospital cover, with exclusions; an elevated one goes to
          a doctor first. Ratings available: {data.ratings.filter((r) => r).map((r) => `+${r}%`).join(', ')}.
        </Text>
      </Alert>

      <Card p="md">
        <Text fw={700} mb="xs">
          What clients pay at these assumptions
        </Text>
        <Table.ScrollContainer minWidth={640}>
          <Table fz="sm" verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Age</Table.Th>
                <Table.Th ta="right">Term life, 10 lakh, 10 years: man</Table.Th>
                <Table.Th ta="right">woman</Table.Th>
                <Table.Th ta="right">Hospital cover, 2 lakh a year</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {[25, 35, 45, 55].map((age) => {
                const at = (product: string, sex: string) =>
                  examples.find((e) => e.age === age && e.product === product && e.sex === sex)
                const cell = (e?: { monthlyBdt: number; annualBdt: number }) =>
                  e && e.annualBdt > 0 ? `${taka(e.monthlyBdt)}/mo · ${taka(e.annualBdt)}/yr` : 'Not offered'
                return (
                  <Table.Tr key={age}>
                    <Table.Td>{age}</Table.Td>
                    <Table.Td ta="right">{cell(at('life', 'male'))}</Table.Td>
                    <Table.Td ta="right">{cell(at('life', 'female'))}</Table.Td>
                    <Table.Td ta="right">{cell(at('health', 'any'))}</Table.Td>
                  </Table.Tr>
                )
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>

      <Calculator lifeAmounts={data.lifeAmounts} lifeTerms={data.lifeTerms} healthAmounts={data.healthAmounts} ratings={data.ratings} />

      <PricingPolicyCard />
    </Stack>
  )
}

function Calculator({
  lifeAmounts,
  lifeTerms,
  healthAmounts,
  ratings,
}: {
  lifeAmounts: number[]
  lifeTerms: number[]
  healthAmounts: number[]
  ratings: number[]
}) {
  const [product, setProduct] = useState<'life' | 'health'>('life')
  const [amount, setAmount] = useState<number>(1_000_000)
  const [term, setTerm] = useState<number>(10)
  const [age, setAge] = useState<number>(35)
  const [sex, setSex] = useState<string>('male')
  const [smoker, setSmoker] = useState(false)
  const [rating, setRating] = useState(0)
  const amounts = product === 'life' ? lifeAmounts : healthAmounts
  const sum = amounts.includes(amount) ? amount : amounts[0]
  const { data } = useQuery({
    queryKey: ['quote', product, sum, term, age, sex, smoker, rating],
    queryFn: () => quote({ product, sumAssuredBdt: sum, termYears: term, age, sex, smoker, ratingPct: rating }),
  })
  return (
    <Card p="md">
      <Text fw={700} mb="xs">
        Price a policy
      </Text>
      <Group align="flex-end" gap="sm" wrap="wrap">
        <SegmentedControl
          size="xs"
          value={product}
          onChange={(v) => setProduct(v as 'life' | 'health')}
          data={[
            { value: 'life', label: 'Term life' },
            { value: 'health', label: 'Hospital cover' },
          ]}
        />
        <Select size="xs" label="Amount" w={130} data={amounts.map((a) => ({ value: String(a), label: lakh(a) }))} value={String(sum)} onChange={(v) => v && setAmount(Number(v))} allowDeselect={false} />
        {product === 'life' && (
          <Select size="xs" label="Years" w={90} data={lifeTerms.map(String)} value={String(term)} onChange={(v) => v && setTerm(Number(v))} allowDeselect={false} />
        )}
        <NumberInput size="xs" label="Age" w={80} min={18} max={70} value={age} onChange={(v) => setAge(Number(v) || 18)} />
        <Select
          size="xs"
          label="Sex"
          w={100}
          data={[
            { value: 'male', label: 'Male' },
            { value: 'female', label: 'Female' },
          ]}
          value={sex}
          onChange={(v) => v && setSex(v)}
          allowDeselect={false}
        />
        <Select size="xs" label="Rating" w={110} data={ratings.map((r) => ({ value: String(r), label: r ? `+${r}%` : 'Standard' }))} value={String(rating)} onChange={(v) => v && setRating(Number(v))} allowDeselect={false} />
        <Checkbox size="xs" label="Smoker" checked={smoker} onChange={(e) => setSmoker(e.currentTarget.checked)} mb={6} />
      </Group>
      {data && (
        <Text size="sm" mt="sm" fw={600} c={data.eligible ? undefined : 'red'}>
          {data.eligible
            ? `${taka(data.monthlyBdt)} a month, or ${taka(data.annualBdt)} a year. Expected claims about ${taka(data.expectedClaimsBdt)} a year; the rest pays costs and profit.`
            : data.reason}
        </Text>
      )}
    </Card>
  )
}
