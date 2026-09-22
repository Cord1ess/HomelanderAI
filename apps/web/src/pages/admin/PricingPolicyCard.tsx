import { Button, Card, Group, NumberInput, Stack, Table, Text } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { getTenantSettings, updateTenantSettings } from '../../api/client'
import { LastChanged } from './LastChanged'

const BDT = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const PREVIEW_COVERS = [500_000, 1_000_000, 2_500_000, 5_000_000]

interface Draft {
  premiumLowBdt: number
  premiumModerateBdt: number
  referenceCoverBdt: number
}

/**
 * What the two quotable plans cost. The monthly premium is stated at a
 * reference cover and scales in a straight line with the cover a client asks
 * for: twice the cover, twice the premium.
 *
 * Elevated and unscorable applications have no rate here on purpose: a price
 * on a case a person has not yet looked at would imply an outcome that has not
 * been decided.
 */
export function PricingPolicyCard() {
  const queryClient = useQueryClient()
  const { data, error } = useQuery({ queryKey: ['tenant-settings'], queryFn: getTenantSettings })

  const [edited, setEdited] = useState<Draft | undefined>(undefined)
  const current: Draft | undefined = data
    ? {
        premiumLowBdt: data.premiumLowBdt,
        premiumModerateBdt: data.premiumModerateBdt,
        referenceCoverBdt: data.referenceCoverBdt,
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
      notifications.show({
        title: 'Saved',
        message: 'Every screen that shows a premium now uses these rates.',
        color: 'teal',
      })
    },
    onError: (err) => {
      notifications.show({
        title: 'Could not save',
        message: err instanceof Error ? err.message : 'Unknown error',
        color: 'red',
      })
    },
  })

  const unchanged =
    !value ||
    !current ||
    (value.premiumLowBdt === current.premiumLowBdt &&
      value.premiumModerateBdt === current.premiumModerateBdt &&
      value.referenceCoverBdt === current.referenceCoverBdt)
  const invalid =
    !value || value.premiumLowBdt <= 0 || value.premiumModerateBdt <= 0 || value.referenceCoverBdt <= 0

  const set = (patch: Partial<Draft>) => value && setEdited({ ...value, ...patch })
  const premium = (base: number, cover: number) =>
    value ? Math.round(base * (cover / value.referenceCoverBdt)) : 0

  return (
    <Card p="sm">
      <Text size="xs" c="dimmed" fw={600}>
        Pricing policy
      </Text>
      <Text size="sm" mt={4} mb="xs">
        The monthly premium for each plan at the reference cover. A client asking for twice the
        reference cover is quoted twice the premium. Elevated-risk applications carry no rate until
        a medical professional decides.
      </Text>

      {value && (
        <Stack gap="sm">
          <Group align="flex-end" gap="sm" wrap="wrap">
            <NumberInput
              size="xs"
              label="Standard plan (low tier)"
              description="Monthly, in taka"
              min={1}
              thousandSeparator=","
              w={170}
              value={value.premiumLowBdt}
              onChange={(v) => set({ premiumLowBdt: Number(v) || 0 })}
            />
            <NumberInput
              size="xs"
              label="With adjustment (moderate tier)"
              description="Monthly, in taka"
              min={1}
              thousandSeparator=","
              w={190}
              value={value.premiumModerateBdt}
              onChange={(v) => set({ premiumModerateBdt: Number(v) || 0 })}
            />
            <NumberInput
              size="xs"
              label="Reference cover"
              description="The cover those premiums are for"
              min={1}
              thousandSeparator=","
              w={170}
              value={value.referenceCoverBdt}
              onChange={(v) => set({ referenceCoverBdt: Number(v) || 0 })}
            />
          </Group>
          <Group gap="sm">
            <Button
              size="xs"
              onClick={() => save.mutate()}
              loading={save.isPending}
              disabled={unchanged || invalid}
            >
              Save
            </Button>
            {edited && !unchanged && (
              <Button size="xs" variant="subtle" onClick={() => setEdited(undefined)}>
                Reset
              </Button>
            )}
          </Group>

          {/* Preview: what the proposed rates quote at the covers people ask for. */}
          <Table fz="xs" withRowBorders={false} verticalSpacing={2}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Cover</Table.Th>
                <Table.Th>Standard</Table.Th>
                <Table.Th>With adjustment</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {PREVIEW_COVERS.map((cover) => (
                <Table.Tr key={cover}>
                  <Table.Td ff="monospace">৳{BDT.format(cover)}</Table.Td>
                  <Table.Td ff="monospace" className="pricing-preview__cell">
                    ৳{BDT.format(premium(value.premiumLowBdt, cover))}
                  </Table.Td>
                  <Table.Td ff="monospace" className="pricing-preview__cell">
                    ৳{BDT.format(premium(value.premiumModerateBdt, cover))}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          <Text size="xs" style={{ color: 'var(--neo-muted)' }}>
            Monthly premiums the proposed rates would quote. Illustrative, not actuarial: the
            underwriter sets the final rate on every approval.
          </Text>
        </Stack>
      )}

      {error && (
        <Text size="xs" style={{ color: 'var(--neo-danger)' }}>
          Could not load the current rates.
        </Text>
      )}
      <LastChanged fields={['premium_low_bdt', 'premium_moderate_bdt', 'reference_cover_bdt']} />
    </Card>
  )
}
