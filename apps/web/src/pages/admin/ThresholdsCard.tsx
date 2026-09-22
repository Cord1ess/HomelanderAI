import { Button, Card, Group, NumberInput, RangeSlider, SimpleGrid, Stack, Text } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { getQueue, getTenantSettings, updateTenantSettings } from '../../api/client'
import { TIER_META } from '../../components/TierBadge'
import { LastChanged } from './LastChanged'

/**
 * The two boundaries that turn a score into a tier: low up to the first,
 * moderate up to the second, elevated above that.
 *
 * Every score keeps the boundaries it was tiered with, so moving these changes
 * how future scores are tiered and nothing else. The preview below shows how
 * the company's existing scores would fall under the proposed boundaries, so
 * the effect of a change is visible before it is saved, without pretending the
 * existing scores will move.
 */
export function ThresholdsCard() {
  const queryClient = useQueryClient()
  const { data, error } = useQuery({ queryKey: ['tenant-settings'], queryFn: getTenantSettings })

  // Scores across the company's applications, for the preview only.
  const { data: queue } = useQuery({
    queryKey: ['applications', 'all', ''],
    queryFn: () => getQueue({}),
    staleTime: 30_000,
  })
  const scores = (queue?.items ?? []).map((i) => i.crs).filter((c): c is number => c != null)

  // Displayed values are the edit if there is one, else the loaded setting.
  const [edited, setEdited] = useState<[number, number] | undefined>(undefined)
  const current: [number, number] | undefined = data ? [data.tierLowMax, data.tierModerateMax] : undefined
  const value = edited ?? current

  const save = useMutation({
    mutationFn: () => updateTenantSettings({ tierLowMax: value![0], tierModerateMax: value![1] }),
    onSuccess: () => {
      setEdited(undefined)
      void queryClient.invalidateQueries({ queryKey: ['tenant-settings'] })
      void queryClient.invalidateQueries({ queryKey: ['tenant-settings-history'] })
      void queryClient.invalidateQueries({ queryKey: ['pricing'] })
      notifications.show({
        title: 'Saved',
        message: 'New scores are tiered with the new boundaries. Existing scores keep theirs.',
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

  const unchanged = !value || !current || (value[0] === current[0] && value[1] === current[1])
  const invalid = !value || value[0] <= 0 || value[1] >= 100 || value[0] >= value[1]

  const tierOf = (crs: number, [low, moderate]: [number, number]) =>
    crs <= low ? 'low' : crs <= moderate ? 'moderate' : 'elevated'
  const count = (bounds: [number, number], tier: string) =>
    scores.filter((c) => tierOf(c, bounds) === tier).length

  return (
    <Card p="sm">
      <Text size="xs" c="dimmed" fw={600}>
        Risk-score boundaries
      </Text>
      <Text size="sm" mt={4} mb="xs">
        A score from 0 to 100 becomes a tier: <strong>low</strong> up to the first boundary,{' '}
        <strong>moderate</strong> up to the second, <strong>elevated</strong> above that. Elevated
        applications can only be decided by a medical professional.
      </Text>

      {value && (
        <Stack gap="sm">
          <RangeSlider
            min={1}
            max={99}
            step={0.5}
            minRange={1}
            value={value}
            onChange={(v) => setEdited([v[0], v[1]])}
            label={(v) => v.toFixed(1)}
            color="clinical"
            marks={[
              { value: 25, label: '25' },
              { value: 50, label: '50' },
              { value: 75, label: '75' },
            ]}
            aria-label="Tier boundaries"
            mb="md"
          />
          <Group align="flex-end" gap="sm" wrap="wrap">
            <NumberInput
              size="xs"
              label="Low up to"
              min={1}
              max={99}
              step={0.5}
              decimalScale={1}
              w={110}
              value={value[0]}
              onChange={(v) => setEdited([Number(v) || 0, value[1]])}
            />
            <NumberInput
              size="xs"
              label="Moderate up to"
              min={1}
              max={99}
              step={0.5}
              decimalScale={1}
              w={110}
              value={value[1]}
              onChange={(v) => setEdited([value[0], Number(v) || 0])}
            />
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
          {invalid && (
            <Text size="xs" style={{ color: 'var(--neo-danger)' }}>
              The low boundary must be below the moderate boundary, and both between 1 and 99.
            </Text>
          )}

          {/* Preview: how the company's existing scores would fall. */}
          {scores.length > 0 && current && (
            <div>
              <Text size="xs" fw={600} mb={4}>
                Of the {scores.length} scored application{scores.length === 1 ? '' : 's'} today
              </Text>
              <SimpleGrid cols={3} spacing="xs">
                {(['low', 'moderate', 'elevated'] as const).map((tier) => {
                  const now = count(current, tier)
                  const proposed = count(value, tier)
                  return (
                    <div key={tier} className="threshold-preview" data-tier={tier}>
                      <Text size="xs" c={TIER_META[tier].color} fw={600}>
                        {TIER_META[tier].label}
                      </Text>
                      <Text size="sm" fw={700} className="threshold-preview__count">
                        {proposed}
                        {proposed !== now && (
                          <Text span size="xs" fw={500} style={{ color: 'var(--neo-muted)' }}>
                            {' '}
                            (now {now})
                          </Text>
                        )}
                      </Text>
                    </div>
                  )
                })}
              </SimpleGrid>
              <Text size="xs" mt={4} style={{ color: 'var(--neo-muted)' }}>
                A preview only. Scores already computed keep the boundaries they were tiered
                with; this shows how the same scores would fall under the proposed ones.
              </Text>
            </div>
          )}
        </Stack>
      )}

      {error && (
        <Text size="xs" style={{ color: 'var(--neo-danger)' }}>
          Could not load the current boundaries.
        </Text>
      )}
      <LastChanged fields={['tier_low_max', 'tier_moderate_max']} />
    </Card>
  )
}
