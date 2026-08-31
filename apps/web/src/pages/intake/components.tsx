import { Badge, Group, Stack, Text, type StackProps } from '@mantine/core'

/**
 * A numbered intake section with its completion indicator. Reused across the
 * one-page intake form.
 */
export function Section({
  n,
  title,
  complete,
  children,
  ...rest
}: {
  n: string
  title: string
  complete: boolean
  children: React.ReactNode
} & StackProps) {
  return (
    <Stack gap="sm" {...rest}>
      <Group gap="xs" justify="space-between">
        <Group gap="xs">
          <Badge color="clinical" variant="light" radius="sm">
            {n}
          </Badge>
          <Text fw={600} size="sm">
            {title}
          </Text>
        </Group>
        <Badge
          size="xs"
          color={complete ? 'teal' : 'gray'}
          variant={complete ? 'light' : 'outline'}
        >
          {complete ? 'Complete' : 'Incomplete'}
        </Badge>
      </Group>
      {children}
    </Stack>
  )
}
