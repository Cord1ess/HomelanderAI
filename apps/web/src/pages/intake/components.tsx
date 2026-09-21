import { Badge, Box, Group, Stack, Text, type StackProps } from '@mantine/core'

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
    <Box
      style={{
        backgroundColor: 'var(--mantine-color-dark-6)',
        border: '1px solid rgba(212, 222, 149, 0.14)',
        borderRadius: '8px',
        padding: '1.25rem',
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.28)',
      }}
    >
      <Stack gap="md" {...rest}>
        <Group
          gap="xs"
          justify="space-between"
          pb="xs"
          style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.09)' }}
        >
          <Group gap="xs">
            <Badge color="clinical" variant="filled" radius="sm" size="sm">
              Section {n}
            </Badge>
            <Text fw={700} size="sm" c="var(--mantine-color-dark-0)">
              {title}
            </Text>
          </Group>
          <Badge
            size="xs"
            color={complete ? 'teal' : 'gray'}
            variant={complete ? 'filled' : 'outline'}
          >
            {complete ? 'Complete' : 'Incomplete'}
          </Badge>
        </Group>
        {children}
      </Stack>
    </Box>
  )
}
