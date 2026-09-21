import { Badge, Card, Divider, Group, Select, Stack, Switch, Text } from '@mantine/core'
import { IconBell, IconVolume } from '@tabler/icons-react'
import { useState } from 'react'

export function ConsolePreferencesCard() {
  const [inAppAlerts, setInAppAlerts] = useState(true)
  const [soundCues, setSoundCues] = useState(true)
  const [refreshInterval, setRefreshInterval] = useState<string | null>('30')

  return (
    <Card>
      <Group justify="space-between" mb="xs">
        <Text fw={600} size="sm">
          Console & Triage Preferences
        </Text>
        <IconBell size={16} />
      </Group>
      <Divider mb="sm" />

      <Stack gap="md">
        <Group justify="space-between" wrap="nowrap">
          <div>
            <Text size="xs" fw={600}>
              In-app notification badge
            </Text>
            <Text size="xs" c="dimmed">
              Alert when applications finish AI scoring or arrive for review.
            </Text>
          </div>
          <Switch
            checked={inAppAlerts}
            onChange={(e) => setInAppAlerts(e.currentTarget.checked)}
            color="clinical"
            size="sm"
          />
        </Group>

        <Group justify="space-between" wrap="nowrap">
          <div>
            <Text size="xs" fw={600}>
              Audio triage chime
            </Text>
            <Text size="xs" c="dimmed">
              Play a subtle sound when high-risk Tier 3 applications are escalated.
            </Text>
          </div>
          <Switch
            checked={soundCues}
            onChange={(e) => setSoundCues(e.currentTarget.checked)}
            color="clinical"
            size="sm"
            thumbIcon={<IconVolume size={10} />}
          />
        </Group>

        <Group justify="space-between" wrap="nowrap">
          <div>
            <Group gap={6}>
              <Text size="xs" fw={600}>
                Email digest
              </Text>
              <Badge size="xs" variant="outline" color="gray">
                Phase 2
              </Badge>
            </Group>
            <Text size="xs" c="dimmed">
              Periodic email digest of pending applications and daily review summaries.
            </Text>
          </div>
          <Switch disabled checked={false} size="sm" />
        </Group>

        <Select
          label="Queue polling interval"
          description="Frequency of background status updates for active triage"
          value={refreshInterval}
          onChange={setRefreshInterval}
          data={[
            { value: '15', label: '15 seconds (High activity)' },
            { value: '30', label: '30 seconds (Standard recommended)' },
            { value: '60', label: '60 seconds (Battery saver)' },
          ]}
        />
      </Stack>
    </Card>
  )
}
