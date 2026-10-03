import { Alert, Badge, Button, Group, Paper, SegmentedControl, Stack, Text } from '@mantine/core'
import { IconAlertTriangle, IconAt, IconChecks } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { getNotifications, markAllNotificationsRead, markNotificationRead } from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { EmptyState, LoadingState } from '../../components/states'

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
const REVIEW_KINDS = new Set([
  'processing_complete',
  'tier_escalation',
  'evidence_requested',
  'documents_uploaded',
  'doctor_reviewed',
])

/** Where a notification leads: its application, or for a request to see a
 * client's details, the place it is answered. */
function linkFor(n: { applicationId?: string | null; notificationType: string }): string | null {
  if (n.applicationId) return `/applications/${n.applicationId}`
  if (n.notificationType === 'access_requested') return '/access-requests'
  if (n.notificationType === 'access_decided') return '/clients'
  return null
}

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

  const markAllRead = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })

  const items = useMemo(() => data ?? [], [data])
  const unreadCount = items.filter((n) => !n.readAt).length
  const visible = filter === 'unread' ? items.filter((n) => !n.readAt) : items

  return (
    <Stack gap="md">
      <PageHeader
        screen="notifications"
        description={unreadCount > 0 ? `${unreadCount} unread.` : 'You are all caught up.'}
        actions={
          <Group gap="xs">
            <Button
              size="xs"
              variant="light"
              leftSection={<IconChecks size={14} />}
              onClick={() => markAllRead.mutate()}
              loading={markAllRead.isPending}
              disabled={unreadCount === 0}
            >
              Mark all as read
            </Button>
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
        }
      />

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
          {isPending && <LoadingState label="Loading notifications" />}

          {!isPending &&
            visible.map((n) => {
              const unread = !n.readAt
              const isEscalation =
                n.notificationType === 'tier_escalation' ||
                n.message.toLowerCase().includes('escalat')

              const body = (
                <>
                  <Group gap="xs" align="center">
                    <Text size="sm" fw={unread ? 600 : 500}>
                      {n.message}
                    </Text>
                    {isEscalation && (
                      <Badge size="xs" variant="light" color="orange">
                        Sent to a doctor
                      </Badge>
                    )}
                    {n.notificationType === 'access_requested' && (
                      <Badge size="xs" variant="light" color="grape">
                        Access request
                      </Badge>
                    )}
                    {n.notificationType === 'documents_uploaded' && (
                      <Badge size="xs" variant="light" color="teal">
                        From the client
                      </Badge>
                    )}
                  </Group>
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
                    backgroundColor: unread
                      ? isEscalation
                        ? 'var(--neo-warn-soft)'
                        : 'var(--neo-accent-soft)'
                      : undefined,
                  }}
                >
                  <Badge
                    size="xs"
                    variant="filled"
                    color={unread ? (isEscalation ? 'orange' : 'clinical') : 'gray'}
                    circle
                  />
                  <Stack gap={1} style={{ flex: 1 }}>
                    {linkFor(n) ? (
                      <Link
                        to={linkFor(n)!}
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
                  {n.notificationType === 'access_requested' && (
                    <Badge size="xs" variant="outline" color="grape">
                      Answer
                    </Badge>
                  )}
                  {REVIEW_KINDS.has(n.notificationType) && (
                    <Badge size="xs" variant="outline" color={isEscalation ? 'orange' : 'gray'}>
                      Review
                    </Badge>
                  )}
                </Group>
              )
            })}

          {!isPending && visible.length === 0 && !error && (
            <EmptyState
              title={filter === 'unread' ? 'Nothing unread' : 'No notifications yet'}
              text="You are told here when an application your company is handling changes: a score lands, a document arrives, a decision is recorded."
            />
          )}
        </Stack>
      </Paper>
    </Stack>
  )
}
