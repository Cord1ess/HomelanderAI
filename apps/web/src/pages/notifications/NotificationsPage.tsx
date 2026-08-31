import {
  Badge,
  Card,
  Container,
  Group,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core'
import { Link } from 'react-router-dom'

/**
 * Notifications — in-app only in Phase 1. No email, no SMS.
 *
 * These go to staff, not applicants. A bell in the header carries the unread
 * count; an item links to its application and marks it read on click.
 *
 * TODO: `GET /api/notifications`; mark read when navigating to the
 * application.
 */

interface Notification {
  id: string
  message: string
  ref: string
  when: string
  unread: boolean
}

const ITEMS: Notification[] = [] // TODO: from useQuery ['notifications']

export function NotificationsPage() {
  return (
    <Container size="md">
      <Stack gap="md">
        <div>
          <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: '0.12em' }}>
            Staff
          </Text>
          <Title order={1}>Notifications</Title>
        </div>

        <Card padding={0}>
          <Table>
            <Table.Tbody>
              {ITEMS.map((n) => (
                <Table.Tr key={n.id}>
                  <Table.Td>
                    <Group gap="sm">
                      {n.unread && <Badge size="xs" color="clinical" variant="filled" />}
                      <Stack gap={2}>
                        <Text size="sm" component={Link} to={`/applications/${n.ref}`}>
                          {n.message}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {n.ref} · {n.when}
                        </Text>
                      </Stack>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
              {ITEMS.length === 0 && (
                <Table.Tr>
                  <Table.Td>
                    <Text ta="center" c="dimmed" py="lg" size="sm">
                      No notifications. Link the notifications query to populate
                      this list.
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Card>
      </Stack>
    </Container>
  )
}
