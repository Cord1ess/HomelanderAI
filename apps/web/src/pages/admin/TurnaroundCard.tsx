import { Button, Card, Group, NumberInput, Text } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { getTenantSettings, updateTenantSettings } from '../../api/client'

/**
 * The one company-wide setting: how long applicants are told a decision
 * usually takes.
 *
 * It is a promise, so it is stated in working days and applied to future
 * applicants only. An application already told "by Wednesday" keeps
 * Wednesday; an underwriter can still revise that one case from its own
 * screen, with a reason.
 */
export function TurnaroundCard() {
  const queryClient = useQueryClient()

  const { data, error } = useQuery({
    queryKey: ['tenant-settings'],
    queryFn: getTenantSettings,
  })

  // What the admin has typed, or undefined until they touch the field. The
  // displayed value is derived from that and the loaded setting, rather than
  // copied from the query into state by an effect — an effect that sets state
  // triggers a second render for no gain, and this is not an external system.
  const [edited, setEdited] = useState<number | '' | undefined>(undefined)
  const days: number | '' = edited ?? data?.turnaroundBusinessDays ?? ''

  const save = useMutation({
    mutationFn: () => updateTenantSettings({ turnaroundBusinessDays: Number(days) }),
    onSuccess: (settings) => {
      setEdited(undefined)
      void queryClient.invalidateQueries({ queryKey: ['tenant-settings'] })
      void queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
      notifications.show({
        title: 'Saved',
        message: `New applicants will be told to expect an answer within ${settings.turnaroundBusinessDays} working days.`,
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

  const unchanged = data !== undefined && days === data.turnaroundBusinessDays
  const invalid = days === '' || Number(days) < 1 || Number(days) > 30

  return (
    <Card p="sm">
      <Text size="xs" c="dimmed" fw={600}>
        Turnaround promise
      </Text>
      <Text size="sm" mt={4} mb="xs">
        Applicants are told a decision usually takes this many working days.
        Weekends are not counted.
      </Text>
      <Group align="flex-end" gap="sm">
        <NumberInput
          size="xs"
          label="Working days"
          min={1}
          max={30}
          w={120}
          value={days}
          onChange={(v) => setEdited(typeof v === 'number' ? v : v === '' ? '' : Number(v))}
          error={error ? 'Could not load the current value' : undefined}
        />
        <Button
          size="xs"
          onClick={() => save.mutate()}
          loading={save.isPending}
          disabled={unchanged || invalid}
        >
          Save
        </Button>
      </Group>
      <Text size="xs" c="dimmed" mt="xs">
        Applies to applications submitted from now on. Dates already given are not moved.
      </Text>
    </Card>
  )
}
