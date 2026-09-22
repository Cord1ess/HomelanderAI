import { Group, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'

import { useAuth } from '../context/AuthContext'
import { SCREENS, describe, type ScreenId } from '../screens'

/**
 * The top of every console screen: a title, one line saying what the screen
 * is for, and the actions that belong to the whole screen on the right.
 *
 * Pass a `screen` id and the title and description come from the registry, so
 * they match the sidebar. Pass `title` / `description` to override for screens
 * whose title is data (the application reference on the review screen).
 */
export function PageHeader({
  screen,
  title,
  description,
  actions,
  children,
}: {
  screen?: ScreenId
  title?: ReactNode
  description?: ReactNode
  /** Buttons that act on the whole screen. */
  actions?: ReactNode
  /** Anything that belongs directly under the header: filters, a summary strip. */
  children?: ReactNode
}) {
  const { user } = useAuth()
  const role = user?.role ?? 'underwriter'
  const entry = screen ? SCREENS[screen] : undefined

  return (
    <Stack gap="sm" className="page-header">
      <Group justify="space-between" align="flex-start" wrap="wrap" gap="md">
        <div style={{ maxWidth: 720 }}>
          <Title order={1} fz="1.35rem" lh={1.25} fw={600}>
            {title ?? entry?.title}
          </Title>
          <Text size="sm" mt={4} style={{ color: 'var(--neo-muted)' }}>
            {description ?? (entry ? describe(entry, role) : null)}
          </Text>
        </div>
        {actions && (
          <Group gap="xs" wrap="wrap">
            {actions}
          </Group>
        )}
      </Group>
      {children}
    </Stack>
  )
}
