import { Badge, Card, Divider, Group, Stack, Text, ThemeIcon } from '@mantine/core'
import { IconAlertCircle, IconCheck } from '@tabler/icons-react'

interface RoleInfo {
  title: string
  shortTitle: string
  color: string
  description: string
  scope: string[]
  restrictions: string[]
}

interface RoleAuthorityCardProps {
  roleInfo: RoleInfo
}

export function RoleAuthorityCard({ roleInfo }: RoleAuthorityCardProps) {
  return (
    <Card>
      <Group justify="space-between" mb="xs">
        <Text fw={600} size="sm">
          What your role lets you do
        </Text>
        <Badge color={roleInfo.color} variant="light">
          {roleInfo.shortTitle}
        </Badge>
      </Group>
      <Divider mb="sm" />

      <Text size="xs" c="dimmed" mb="md">
        {roleInfo.description}
      </Text>

      <Text
        size="xs"
        fw={600}
        c="clinical.4"
        mb={6}
        style={{ textTransform: 'uppercase', letterSpacing: '0.04em' }}
      >
        You can
      </Text>
      <Stack gap={6} mb="md">
        {roleInfo.scope.map((item, idx) => (
          <Group key={idx} gap="xs" wrap="nowrap" align="flex-start">
            <ThemeIcon size={18} variant="light" color="teal" radius="xl">
              <IconCheck size={12} />
            </ThemeIcon>
            <Text size="xs" style={{ flex: 1 }}>
              {item}
            </Text>
          </Group>
        ))}
      </Stack>

      <Text
        size="xs"
        fw={600}
        c="orange.4"
        mb={6}
        style={{ textTransform: 'uppercase', letterSpacing: '0.04em' }}
      >
        You cannot
      </Text>
      <Stack gap={6}>
        {roleInfo.restrictions.map((item, idx) => (
          <Group key={idx} gap="xs" wrap="nowrap" align="flex-start">
            <ThemeIcon size={18} variant="light" color="orange" radius="xl">
              <IconAlertCircle size={12} />
            </ThemeIcon>
            <Text size="xs" c="dimmed" style={{ flex: 1 }}>
              {item}
            </Text>
          </Group>
        ))}
      </Stack>
    </Card>
  )
}
