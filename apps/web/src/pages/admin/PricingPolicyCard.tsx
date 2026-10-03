import { Button, Card, Group, NumberInput, SimpleGrid, Stack, Text } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { getTenantSettings, updateTenantSettings } from '../../api/client'
import { LastChanged } from './LastChanged'

interface Draft {
  lifeExpenseLoadingPct: number
  lifeInterestPct: number
  healthRatePerLakhBdt: number
  smokerLoadingPct: number
  monthlyLoadingPct: number
}

const FIELDS: { key: keyof Draft; label: string; help: string; min: number; max: number; step: number; suffix: string }[] = [
  {
    key: 'lifeExpenseLoadingPct',
    label: 'Life: expense loading',
    help: "Share of the premium for commission, running costs and profit. IDRA's cap for non-participating plans is 22.32%.",
    min: 5,
    max: 22.32,
    step: 0.01,
    suffix: '%',
  },
  {
    key: 'lifeInterestPct',
    label: 'Life: interest assumed',
    help: 'What premiums earn while held. IDRA allows at most 5% for non-participating plans; lower is more prudent.',
    min: 0,
    max: 5,
    step: 0.25,
    suffix: '%',
  },
  {
    key: 'healthRatePerLakhBdt',
    label: 'Hospital cover: yearly rate per ৳1 lakh',
    help: 'For ages 18-35. Older bands pay 1.35×, 1.9×, 2.8× and 3.6× this.',
    min: 300,
    max: 20000,
    step: 50,
    suffix: ' ৳',
  },
  {
    key: 'smokerLoadingPct',
    label: 'Smoker loading',
    help: 'Extra for a client who declared smoking. Smokers die younger and are in hospital more.',
    min: 0,
    max: 200,
    step: 5,
    suffix: '%',
  },
  {
    key: 'monthlyLoadingPct',
    label: 'Paying monthly',
    help: 'Extra for paying in twelve instalments rather than once a year.',
    min: 0,
    max: 15,
    step: 0.5,
    suffix: '%',
  },
]

/**
 * The company's pricing assumptions. The engine (app/pricing.py) prices every
 * policy from these: term life from a Bangladeshi mortality basis, interest
 * and a loading; hospital cover from a yearly rate by age. Changing one here
 * re-prices every quote from now on; policies already issued keep their price.
 */
export function PricingPolicyCard() {
  const queryClient = useQueryClient()
  const { data } = useQuery({ queryKey: ['tenant-settings'], queryFn: getTenantSettings })
  const [edited, setEdited] = useState<Draft | undefined>(undefined)
  const current: Draft | undefined = data
    ? {
        lifeExpenseLoadingPct: data.lifeExpenseLoadingPct,
        lifeInterestPct: data.lifeInterestPct,
        healthRatePerLakhBdt: data.healthRatePerLakhBdt,
        smokerLoadingPct: data.smokerLoadingPct,
        monthlyLoadingPct: data.monthlyLoadingPct,
      }
    : undefined
  const value = edited ?? current

  const save = useMutation({
    mutationFn: () => updateTenantSettings(value!),
    onSuccess: () => {
      setEdited(undefined)
      void queryClient.invalidateQueries({ queryKey: ['tenant-settings'] })
      void queryClient.invalidateQueries({ queryKey: ['tenant-settings-history'] })
      void queryClient.invalidateQueries({ queryKey: ['pricing'] })
      notifications.show({ title: 'Saved', message: 'New quotes use these assumptions. Issued policies keep their price.', color: 'teal' })
    },
    onError: (err) =>
      notifications.show({ title: 'Could not save', message: err instanceof Error ? err.message : 'Unknown error', color: 'red' }),
  })

  const unchanged = !value || !current || FIELDS.every((f) => value[f.key] === current[f.key])

  return (
    <Card p="sm">
      <Text size="xs" c="dimmed" fw={600}>
        Pricing assumptions
      </Text>
      <Text size="sm" mt={4} mb="xs">
        Every premium is worked out from these. Term life uses a Bangladeshi mortality basis (3 deaths per 1,000 at 35,
        rising 8% a year of age; women 80% of that); hospital cover a yearly rate by age.
      </Text>
      {value && (
        <Stack gap="sm">
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            {FIELDS.map((f) => (
              <NumberInput
                key={f.key}
                size="xs"
                label={f.label}
                description={f.help}
                min={f.min}
                max={f.max}
                step={f.step}
                decimalScale={2}
                suffix={f.suffix}
                thousandSeparator=","
                value={value[f.key]}
                onChange={(v) => setEdited({ ...value, [f.key]: Number(v) || 0 })}
              />
            ))}
          </SimpleGrid>
          <Group gap="sm">
            <Button size="xs" onClick={() => save.mutate()} loading={save.isPending} disabled={unchanged}>
              Save
            </Button>
            {edited && !unchanged && (
              <Button size="xs" variant="subtle" onClick={() => setEdited(undefined)}>
                Reset
              </Button>
            )}
          </Group>
          <LastChanged fields={['life_expense_loading_pct', 'life_interest_pct', 'health_rate_per_lakh_bdt', 'smoker_loading_pct', 'monthly_loading_pct']} />
        </Stack>
      )}
    </Card>
  )
}
