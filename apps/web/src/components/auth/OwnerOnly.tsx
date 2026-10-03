import { Paper, Stack, Text, ThemeIcon } from '@mantine/core'
import { IconLock } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

import { useAuth } from '../../context/AuthContext'
import { type ScreenId } from '../../screens'
import { PageHeader } from '../PageHeader'

/**
 * Analytics and Plans and pricing belong to the company owner (an
 * administrator). An underwriter sees them in the sidebar with a lock and,
 * opening one, is told whose it is rather than shown an error. A doctor never
 * sees them and is taken to their own reviews. The API refuses the same
 * people regardless.
 */
export function OwnerOnly({ screen, children }: { screen: ScreenId; children: ReactNode }) {
  const { user } = useAuth()
  if (user?.role === 'admin') return <>{children}</>
  if (user?.role === 'medical_professional') return <Navigate to="/escalations" replace />

  return (
    <Stack gap="lg" maw={720}>
      <PageHeader screen={screen} />
      <Paper p="xl" bd="1px solid var(--mantine-color-default-border)">
        <Stack align="center" gap="sm" ta="center">
          <ThemeIcon size={48} radius="xl" variant="light" color="gray">
            <IconLock size={24} />
          </ThemeIcon>
          <Text fw={700}>Only the company owner can open this</Text>
          <Text size="sm" c="dimmed" maw={460}>
            This page belongs to your company's administrator. If you need something from it,
            ask them directly.
          </Text>
        </Stack>
      </Paper>
    </Stack>
  )
}
