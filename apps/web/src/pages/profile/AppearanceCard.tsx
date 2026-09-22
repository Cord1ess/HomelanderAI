import { Card, Divider, Group, SegmentedControl, Text, useMantineColorScheme } from '@mantine/core'
import { IconSunMoon } from '@tabler/icons-react'

/**
 * The one console preference that exists: light, dark, or whatever the device
 * uses. Remembered in this browser. The same choice is behind the sun/moon
 * button in the header.
 */
export function AppearanceCard() {
  const { colorScheme, setColorScheme } = useMantineColorScheme()

  return (
    <Card>
      <Group justify="space-between" mb="xs">
        <Text fw={600} size="sm">
          Appearance
        </Text>
        <IconSunMoon size={16} />
      </Group>
      <Divider mb="sm" />
      <Text size="xs" c="dimmed" mb="sm">
        Light or dark, or follow whatever this device uses. Remembered in this browser only.
      </Text>
      <SegmentedControl
        fullWidth
        size="xs"
        value={colorScheme}
        onChange={(v) => setColorScheme(v as 'light' | 'dark' | 'auto')}
        data={[
          { value: 'auto', label: 'Follow device' },
          { value: 'light', label: 'Light' },
          { value: 'dark', label: 'Dark' },
        ]}
      />
    </Card>
  )
}
