import { Alert, Badge, Group, Paper, SegmentedControl, Skeleton, Stack, Text } from '@mantine/core'
import { IconAlertTriangle, IconAt } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { getNotifications, markNotificationRead } from '../../api/client'

/**
 * Notifications — in-app only in Phase 1. No email, no SMS.
 *
 * These go to staff, not applicants. A bell in the header carries the unread
 * count; an item links to its application and marks itself read on click.
 */

function relativeTime(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  return days === 1 ? '1 d ago' : `${days} d ago`
}

/** Anything that puts an application in front of an underwriter. */
const REVIEW_KINDS = new Set(['processing_complete', 'tier_escalation', 'evidence_requested'])

export function NotificationsPage() {
  const [filter, setFilter] = useState<'all' | 'unread'>('all')
  const queryClient = useQueryClient()

  const { data, isPending, error } = useQuery({
    queryKey: ['notifications'],
    queryFn: getNotifications,
    refetchInterval: 30_000,
  })

  const markRead = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })

  const items = useMemo(() => data ?? [], [data])
  const unreadCount = items.filter((n) => !n.readAt).length
  const visible = filter === 'unread' ? items.filter((n) => !n.readAt) : items

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <div>
          <Text size="sm" fw={600}>
            Notifications
          </Text>
          <Text size="xs" c="dimmed">
            {unreadCount > 0 ? `${unreadCount} unread` : 'You are all caught up'}
          </Text>
        </div>
        <SegmentedControl
          size="xs"
          value={filter}
          onChange={(v) => setFilter(v as 'all' | 'unread')}
          data={[
            { value: 'all', label: `All (${items.length})` },
            { value: 'unread', label: `Unread (${unreadCount})` },
          ]}
        />
      </Group>

      {error && (
        <Alert
          color="red"
          variant="light"
          icon={<IconAlertTriangle size={16} />}
          title="Could not load notifications"
        >
          {error instanceof Error ? error.message : 'Unknown error'}
        </Alert>
      )}

      <Paper bd="1px solid var(--mantine-color-default-border)" p={0} style={{ overflow: 'hidden' }}>
        <Stack gap={0}>
          {isPending && (
            <Stack gap="xs" p="md">
              <Skeleton height={16} />
              <Skeleton height={16} />
              <Skeleton height={16} />
            </Stack>
          )}

          {!isPending &&
            visible.map((n) => {
              const unread = !n.readAt
              const body = (
                <>
                  <Text size="sm" fw={unread ? 600 : 500}>
                    {n.message}
                  </Text>
                  <Group gap="xs">
                    <IconAt size={12} />
                    <Text size="xs" c="dimmed">
                      {n.reference ?? '—'} · {relativeTime(n.createdAt)}
                    </Text>
                  </Group>
                </>
              )

              return (
                <Group
                  key={n.id}
                  px="md"
                  py="sm"
                  gap="sm"
                  wrap="nowrap"
                  style={{
                    borderBottom: '1px solid var(--mantine-color-default-border)',
                    backgroundColor: unread ? 'var(--mantine-color-dark-6)' : undefined,
                  }}
                >
                  <Badge size="xs" variant="filled" color={unread ? 'clinical' : 'gray'} circle />
                  <Stack gap={1} style={{ flex: 1 }}>
                    {n.applicationId ? (
                      <Link
                        to={`/applications/${n.applicationId}`}
                        onClick={() => {
                          if (unread) markRead.mutate(n.id)
                        }}
                        style={{ textDecoration: 'none', color: 'inherit' }}
                      >
                        {body}
                      </Link>
                    ) : (
                      body
                    )}
                  </Stack>
                  {REVIEW_KINDS.has(n.notificationType) && (
                    <Badge size="xs" variant="outline" color="gray">
                      Review
                    </Badge>
                  )}
                </Group>
              )
            })}

          {!isPending && visible.length === 0 && !error && (
            <Text ta="center" c="dimmed" py="lg" size="sm">
              No {filter === 'unread' ? 'unread ' : ''}notifications.
            </Text>
          )}
        </Stack>
      </Paper>
    </Stack>
  )
}
