import { Button, Group, Loader, Stack, Text } from '@mantine/core'
import { IconAlertTriangle, IconInbox } from '@tabler/icons-react'
import type { ReactNode } from 'react'

/**
 * The three states every list and every detail screen goes through, drawn the
 * same way everywhere. Each says what is happening in a sentence a person
 * would use, and the error state always offers a way out.
 */

export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="state-block" role="status" aria-live="polite">
      <Loader color="clinical" type="dots" size="sm" />
      <Text size="sm" style={{ color: 'var(--neo-muted)' }}>
        {label}
      </Text>
    </div>
  )
}

export function EmptyState({
  title,
  text,
  action,
}: {
  title: string
  /** Why it is empty, or what would put something here. */
  text?: string
  action?: ReactNode
}) {
  return (
    <div className="state-block">
      <IconInbox size={26} stroke={1.5} style={{ color: 'var(--neo-muted)' }} />
      <Stack gap={2} align="center">
        <Text size="sm" fw={600}>
          {title}
        </Text>
        {text && (
          <Text size="sm" ta="center" maw={420} style={{ color: 'var(--neo-muted)' }}>
            {text}
          </Text>
        )}
      </Stack>
      {action}
    </div>
  )
}

export function ErrorState({
  title,
  error,
  retry,
}: {
  title: string
  error: unknown
  retry?: () => void
}) {
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <div className="state-block state-block--error" role="alert">
      <IconAlertTriangle size={26} stroke={1.5} style={{ color: 'var(--neo-danger)' }} />
      <Stack gap={2} align="center">
        <Text size="sm" fw={600}>
          {title}
        </Text>
        <Text size="sm" ta="center" maw={460} style={{ color: 'var(--neo-muted)' }}>
          {message}
        </Text>
      </Stack>
      {retry && (
        <Group>
          <Button size="xs" variant="default" onClick={retry}>
            Try again
          </Button>
        </Group>
      )}
    </div>
  )
}
