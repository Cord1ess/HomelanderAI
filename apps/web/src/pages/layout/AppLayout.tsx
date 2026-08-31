import {
  ActionIcon,
  AppShell,
  Badge,
  Burger,
  Group,
  Text,
} from '@mantine/core'
import { IconBell } from '@tabler/icons-react'
import { useDisclosure } from '@mantine/hooks'
import { Link, Outlet } from 'react-router-dom'

/**
 * Shared shell for the authenticated dashboard.
 *
 * Header carries the app mark, a "Review a new client" shortcut, and the
 * notifications bell with an unread count. Nav links land on the five Phase 1
 * screens. TODO: wire unread count to `GET /api/notifications`, session to
 * `GET /api/auth/me`, and logout to `POST /api/auth/logout`.
 */
export function AppLayout() {
  const [opened, { toggle }] = useDisclosure()

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 220, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Text ff="monospace" fw={700} size="sm" c="clinical.4">
              ▚
            </Text>
            <Text ff="monospace" fw={600} size="sm" component={Link} to="/">
              HomelanderAI
            </Text>
          </Group>

          <Group gap="sm">
            <ActionIcon
              variant="light"
              component={Link}
              to="/notifications"
              aria-label="Notifications"
            >
              <IconBell size={18} />
              <Badge
                size="xs"
                color="red"
                variant="filled"
                style={{ position: 'absolute', top: 4, right: 4 }}
              >
                0
              </Badge>
            </ActionIcon>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="md">
        <NavLink to="/">Queue</NavLink>
        <NavLink to="/applications/new">Review a new client</NavLink>
        <NavLink to="/notifications">Notifications</NavLink>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  )
}

function NavLink({ to, children }: { to: string; children: string }) {
  return (
    <Text
      component={Link}
      to={to}
      size="sm"
      c="dimmed"
      style={{ textDecoration: 'none', paddingBlock: 6 }}
    >
      {children}
    </Text>
  )
}
