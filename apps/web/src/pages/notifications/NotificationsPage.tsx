import {
  Badge,
  Group,
  Paper,
  SegmentedControl,
  Stack,
  Text,
} from '@mantine/core'
import { IconAt } from '@tabler/icons-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

/**
 * Notifications — in-app only in Phase 1. No email, no SMS.
 *
 * These go to staff, not applicants. A bell in the header carries the unread
 * count; an item links to its application and marks it read on click.
 *
 * Rows below are STUB data so the list renders; TODO: `GET /api/notifications`.
 * Mark-read is local state until the read endpoint exists.
 */

interface Notification {
  id: string
  message: string
  ref: string
  when: string
  unread: boolean
  kind: 'review' | 'system'
}

const ITEMS: Notification[] = [
  { id: 'n1', message: 'Scoring complete — ready for review', ref: 'APP-2026-0091', when: '2 m ago', unread: true, kind: 'review' },
  { id: 'n2', message: 'More evidence requested for this application', ref: 'APP-2026-0094', when: '31 m ago', unread: true, kind: 'review' },
  { id: 'n3', message: 'New application submitted', ref: 'APP-2026-0096', when: '5 h ago', unread: true, kind: 'system' },
  { id: 'n4', message: 'Scoring complete — ready for review', ref: 'APP-2026-0093', when: '1 d ago', unread: false, kind: 'review' },
  { id: 'n5', message: 'Decision recorded by another underwriter', ref: 'APP-2026-0097', when: '2 d ago', unread: false, kind: 'system' },
]

export function NotificationsPage() {
  const [filter, setFilter] = useState<'all' | 'unread'>('all')
  const [items, setItems] = useState<Notification[]>(ITEMS)

  const unreadCount = items.filter((n) => n.unread).length

  const visible = useMemo(
    () => (filter === 'unread' ? items.filter((n) => n.unread) : items),
    [filter, items],
  )

  const markRead = (id: string) =>
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, unread: false } : n)))

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <div>
          <Text size="sm" fw={600}>
            Notifications
          </Text>
          <Text size="xs" c="dimmed">
            {unreadCount > 0
              ? `${unreadCount} unread`
              : 'You are all caught up'}
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

      <Paper bd="1px solid var(--mantine-color-default-border)" p={0} style={{ overflow: 'hidden' }}>
        <Stack gap={0}>
          {visible.map((n) => (
            <Group
              key={n.id}
              px="md"
              py="sm"
              gap="sm"
              wrap="nowrap"
              style={{
                borderBottom: '1px solid var(--mantine-color-default-border)',
                backgroundColor: n.unread
                  ? 'var(--mantine-color-clinical-0)'
                  : undefined,
              }}
            >
              <Badge
                size="xs"
                variant="filled"
                color={n.unread ? 'clinical' : 'gray'}
                circle
              />
              <Stack gap={1} style={{ flex: 1 }}>
                <Text size="sm" fw={n.unread ? 600 : 500}>
                  <Link
                    to={`/applications/${n.ref}`}
                    onClick={() => markRead(n.id)}
                    style={{ textDecoration: 'none', color: 'inherit' }}
                  >
                    {n.message}
                  </Link>
                </Text>
                <Group gap="xs">
                  <IconAt size={12} />
                  <Text size="xs" c="dimmed">
                    {n.ref} · {n.when}
                  </Text>
                </Group>
              </Stack>
              {n.kind === 'review' && (
                <Badge size="xs" variant="outline" color="gray">
                  Review
                </Badge>
              )}
            </Group>
          ))}
          {visible.length === 0 && (
            <Text ta="center" c="dimmed" py="lg" size="sm">
              No {filter === 'unread' ? 'unread' : ''} notifications.
            </Text>
          )}
        </Stack>
      </Paper>
    </Stack>
  )
}
