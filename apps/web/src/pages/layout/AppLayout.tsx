import {
  ActionIcon,
  AppShell,
  Badge,
  Box,
  Burger,
  Group,
  Menu,
  Text,
  ThemeIcon,
  Tooltip,
  UnstyledButton,
  useMantineColorScheme,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import {
  IconBell,
  IconChevronsLeft,
  IconChevronsRight,
  IconFilePlus,
  IconLayoutDashboard,
  IconLogout,
  IconMoon,
  IconSun,
  IconUser,
} from '@tabler/icons-react'
import type { JSX } from 'react'
import { NavLink as RouterLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { BrandIcon } from '../../components/BrandIcon'
import { useAuth } from '../../auth/AuthContext'

/**
 * ERP-style shell for the authenticated dashboard.
 *
 * A fixed, collapsible icon sidebar mirrors an underwriting console: a compact
 * brand lockup up top, icon nav with tooltips, and a thin header carrying the
 * current screen title, the notifications bell and a user menu.
 *
 * TODO: unread count → `GET /api/notifications`; session → `GET /api/auth/me`;
 * logout → `POST /api/auth/logout`.
 */
export function AppLayout() {
  const [navOpened, { toggle: toggleNav }] = useDisclosure(true)
  const [mobileOpened, { toggle: toggleMobile }] = useDisclosure(false)
  const location = useLocation()

  const title = routeFor(location.pathname)?.title
  const unread = 3

  return (
    <AppShell
      header={{ height: 44 }}
      navbar={{
        width: navOpened ? 200 : 56,
        breakpoint: 'sm',
        collapsed: { mobile: !mobileOpened },
      }}
      padding="md"
      transitionDuration={150}
    >
      <AppShell.Header>
        <Group h="100%" px="sm" justify="space-between" gap="sm" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger
              opened={mobileOpened}
              onClick={toggleMobile}
              hiddenFrom="sm"
              size="sm"
            />
            <ActionIcon
              variant="subtle"
              aria-label="Toggle sidebar"
              onClick={toggleNav}
              visibleFrom="sm"
            >
              {navOpened ? (
                <IconChevronsLeft size={16} />
              ) : (
                <IconChevronsRight size={16} />
              )}
            </ActionIcon>
            <Text size="sm" fw={600}>
              {title}
            </Text>
          </Group>

          <Group gap={6} wrap="nowrap">
            <ActionIcon
              variant="subtle"
              component={RouterLink}
              to="/notifications"
              aria-label="Notifications"
            >
              <IconBell size={18} />
              {unread > 0 && (
                <Badge
                  size="xs"
                  color="red"
                  variant="filled"
                  style={{ position: 'absolute', top: 2, right: 2 }}
                >
                  {unread}
                </Badge>
              )}
            </ActionIcon>
            <UserMenu />
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar className="hl-shell-nav">
        <Group px={navOpened ? 'xs' : 0} py="xs" justify="center">
          <Box
            style={{
              width: navOpened ? 88 : 40,
              height: navOpened ? 88 : 40,
              borderRadius: '50%',
              overflow: 'hidden',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: '#fff',
              border: '1px solid rgba(255,255,255,0.16)',
              boxShadow: '0 2px 10px rgba(0,0,0,0.35), inset 0 0 0 1px rgba(0,0,0,0.04)',
            }}
          >
            <BrandIcon
              width={navOpened ? 68 : 30}
              height={navOpened ? 68 : 30}
              style={{ display: 'block', flex: 'none' }}
            />
          </Box>
        </Group>

        <Box flex={1} mt="xs">
          {NAV.map((item) => (
            <NavItem
              key={item.to}
              to={item.to}
              label={item.label}
              icon={item.icon}
              collapsed={!navOpened}
              active={location.pathname.startsWith(item.to)}
            />
          ))}
        </Box>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  )
}

const NAV: { to: string; label: string; icon: () => JSX.Element }[] = [
  { to: '/queue', label: 'Queue', icon: () => <IconLayoutDashboard size={18} /> },
  { to: '/applications/new', label: 'New application', icon: () => <IconFilePlus size={18} /> },
  { to: '/notifications', label: 'Notifications', icon: () => <IconBell size={18} /> },
]

function routeFor(path: string) {
  if (path === '/queue') return { title: 'Review queue' }
  if (path.startsWith('/applications/new')) return { title: 'New application' }
  if (path.startsWith('/applications/')) return { title: 'Underwriting review' }
  if (path.startsWith('/notifications')) return { title: 'Notifications' }
  return { title: 'HomelanderAI' }
}

function NavItem({
  to,
  label,
  icon,
  collapsed,
  active,
}: {
  to: string
  label: string
  icon: () => JSX.Element
  collapsed: boolean
  active: boolean
}) {
  const link = (
    <RouterLink
      to={to}
      className="hl-nav-link"
      data-active={active}
      style={
        collapsed
          ? { justifyContent: 'center', paddingInline: 0 }
          : undefined
      }
    >
      <ThemeIcon
        variant={active ? 'filled' : 'transparent'}
        color={active ? 'clinical' : 'gray'}
        size={20}
      >
        {icon()}
      </ThemeIcon>
      {!collapsed && <span>{label}</span>}
    </RouterLink>
  )

  if (!collapsed) return link

  return (
    <Tooltip label={label} position="right" withinPortal withArrow>
      {link}
    </Tooltip>
  )
}

function UserMenu() {
  const { colorScheme, toggleColorScheme } = useMantineColorScheme()
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <UnstyledButton aria-label="Account menu">
          <ActionIcon variant="subtle">
            <IconUser size={18} />
          </ActionIcon>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown miw={180}>
        <Menu.Label>signed in as</Menu.Label>
        <Menu.Item leftSection={<IconUser size={14} />}>
          {user?.email ?? 'unknown'}
        </Menu.Item>
        <Menu.Divider />
        <Menu.Item
          leftSection={
            colorScheme === 'dark' ? (
              <IconSun size={14} />
            ) : (
              <IconMoon size={14} />
            )
          }
          onClick={toggleColorScheme}
        >
          Toggle theme
        </Menu.Item>
        <Menu.Divider />
        <Menu.Item
          color="red"
          leftSection={<IconLogout size={14} />}
          onClick={() => {
            signOut()
            navigate('/')
          }}
        >
          Sign out
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  )
}
