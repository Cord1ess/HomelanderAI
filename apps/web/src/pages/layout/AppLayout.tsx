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
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { useQuery } from '@tanstack/react-query'
import {
  IconBell,
  IconChartBar,
  IconChevronsLeft,
  IconChevronsRight,
  IconFilePlus,
  IconFlame,
  IconLayoutList,
  IconLogout,
  IconReceipt,
  IconAddressBook,
  IconSettings,
  IconUser,
  IconUserCircle,
  IconUsers,
} from '@tabler/icons-react'
import type { JSX } from 'react'
import { NavLink as RouterLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { getNotifications } from '../../api/client'
import { BrandIcon } from '../../components/BrandIcon'
import { PageTransition } from '../../components/PageTransition'
import { ThemeToggle } from '../../components/ThemeToggle'
import { useAuth } from '../../context/AuthContext'
import { navFor, type Screen, type ScreenId } from '../../screens'
import { ROLE_LABEL } from '../../types/auth'
import type { UserRole } from '../../types/auth'

/**
 * The console shell: a sidebar of screens for this role, a slim header with
 * the things that are not about any one screen (notifications, theme, account),
 * and the screen itself.
 *
 * The sidebar is built from src/screens.ts, so its labels are the same words
 * as each screen's title. The header carries no title: every screen states its
 * own, with a line under it saying what it is for.
 */
export function AppLayout() {
  const { user, tenant } = useAuth()
  const [navOpened, { toggle: toggleNav }] = useDisclosure(true)
  const [mobileOpened, { toggle: toggleMobile, close: closeMobile }] = useDisclosure(false)
  const location = useLocation()

  const role = user?.role ?? 'underwriter'
  const navItems = navFor(role)

  // Shares its cache key with the notifications screen, so opening one and
  // marking something read updates the badge without a second request.
  const { data: notifications } = useQuery({
    queryKey: ['notifications'],
    queryFn: getNotifications,
    refetchInterval: 30_000,
  })
  const unread = (notifications ?? []).filter((n) => !n.readAt).length

  return (
    <AppShell
      header={{ height: 44 }}
      navbar={{
        width: navOpened ? 232 : 56,
        breakpoint: 'sm',
        collapsed: { mobile: !mobileOpened },
      }}
      padding="lg"
      transitionDuration={200}
    >
      <AppShell.Header>
        <Group h="100%" px="sm" justify="space-between" gap="sm" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={mobileOpened} onClick={toggleMobile} hiddenFrom="sm" size="sm" />
            <Tooltip label={navOpened ? 'Hide the sidebar' : 'Show the sidebar'} withArrow>
              <ActionIcon
                variant="subtle"
                aria-label={navOpened ? 'Hide the sidebar' : 'Show the sidebar'}
                onClick={toggleNav}
                visibleFrom="sm"
              >
                {navOpened ? <IconChevronsLeft size={16} /> : <IconChevronsRight size={16} />}
              </ActionIcon>
            </Tooltip>
            <Text size="sm" fw={600} visibleFrom="xs">
              {tenant?.name ?? 'Homelander AI'}
            </Text>
          </Group>

          <Group gap={6} wrap="nowrap">
            <Tooltip label={unread > 0 ? `${unread} unread` : 'Notifications'} withArrow>
              <ActionIcon
                variant="subtle"
                component={RouterLink}
                to="/notifications"
                aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
              >
                <IconBell size={18} />
                {unread > 0 && (
                  <Badge
                    size="xs"
                    color="red"
                    variant="filled"
                    className="unread-badge"
                    style={{ position: 'absolute', top: 2, right: 2 }}
                  >
                    {unread}
                  </Badge>
                )}
              </ActionIcon>
            </Tooltip>
            <ThemeToggle />
            <UserMenu />
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar className="hl-shell-nav">
        <Group px={navOpened ? 'xs' : 0} py="xs" justify="center">
          <Box
            style={{
              width: navOpened ? 72 : 36,
              height: navOpened ? 72 : 36,
              borderRadius: '50%',
              overflow: 'hidden',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: '#fff', // the mark is drawn for a white disc
              border: '1px solid var(--neo-border-mid)',
              boxShadow: '0 2px 10px var(--neo-shadow)',
              transition: 'width var(--motion-base) var(--ease-out), height var(--motion-base) var(--ease-out)',
            }}
          >
            <BrandIcon
              width={navOpened ? 56 : 28}
              height={navOpened ? 56 : 28}
              style={{ display: 'block', flex: 'none' }}
            />
          </Box>
        </Group>

        <Box flex={1} mt="xs">
          {navItems.map((screen) => (
            <NavItem
              key={screen.id}
              screen={screen}
              collapsed={!navOpened}
              active={isActive(screen, location.pathname)}
              onNavigate={closeMobile}
            />
          ))}
        </Box>

        {/* Who you are, where you are. */}
        <Box px="sm" py="sm" style={{ borderTop: '1px solid var(--neo-border)' }}>
          {navOpened ? (
            <Group gap="xs" wrap="nowrap">
              <Badge color={ROLE_COLOR[role]} variant="filled" size="xs">
                {ROLE_LABEL[role]}
              </Badge>
              <Text size="xs" truncate style={{ color: 'var(--neo-muted)' }}>
                {user?.fullName ?? user?.email ?? ''}
              </Text>
            </Group>
          ) : (
            <Tooltip label={`${user?.fullName ?? ''} (${ROLE_LABEL[role]})`} position="right" withArrow>
              <Group justify="center">
                <Badge color={ROLE_COLOR[role]} variant="filled" size="xs" circle>
                  {ROLE_LABEL[role].charAt(0)}
                </Badge>
              </Group>
            </Tooltip>
          )}
        </Box>
      </AppShell.Navbar>

      <AppShell.Main>
        <PageTransition>
          <Outlet />
        </PageTransition>
      </AppShell.Main>
    </AppShell>
  )
}

/** Badge colour per role. The name comes from ROLE_LABEL, shared with every other screen. */
const ROLE_COLOR: Record<UserRole, string> = {
  underwriter: 'clinical',
  medical_professional: 'grape',
  admin: 'orange',
}

const ICONS: Record<ScreenId, () => JSX.Element> = {
  queue: () => <IconLayoutList size={18} />,
  clients: () => <IconAddressBook size={18} />,
  analytics: () => <IconChartBar size={18} />,
  escalations: () => <IconFlame size={18} />,
  intake: () => <IconFilePlus size={18} />,
  review: () => <IconLayoutList size={18} />,
  pricing: () => <IconReceipt size={18} />,
  staff: () => <IconUsers size={18} />,
  settings: () => <IconSettings size={18} />,
  notifications: () => <IconBell size={18} />,
  profile: () => <IconUserCircle size={18} />,
}

/** An open application belongs to "Applications"; the intake form does not. */
function isActive(screen: Screen, pathname: string): boolean {
  if (pathname === screen.path) return true
  if (screen.id === 'queue') return pathname.startsWith('/applications/') && pathname !== '/applications/new'
  return screen.id !== 'intake' && pathname.startsWith(screen.path)
}

function NavItem({
  screen,
  collapsed,
  active,
  onNavigate,
}: {
  screen: Screen
  collapsed: boolean
  active: boolean
  onNavigate: () => void
}) {
  const link = (
    <RouterLink
      to={screen.path}
      className="hl-nav-link"
      data-active={active}
      aria-current={active ? 'page' : undefined}
      onClick={onNavigate}
      style={collapsed ? { justifyContent: 'center', paddingInline: 0 } : undefined}
    >
      <ThemeIcon
        variant="transparent"
        size={22}
        radius="sm"
        style={{ color: active ? 'var(--neo-forest-ink)' : 'var(--neo-muted)' }}
      >
        {ICONS[screen.id]()}
      </ThemeIcon>
      {!collapsed && (
        <span style={{ fontWeight: active ? 700 : 500, fontSize: '0.825rem' }}>{screen.label}</span>
      )}
    </RouterLink>
  )

  if (!collapsed) return link

  return (
    <Tooltip label={screen.label} position="right" withinPortal withArrow>
      {link}
    </Tooltip>
  )
}

function UserMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <UnstyledButton aria-label="Account menu">
          <ActionIcon variant="subtle" component="span">
            <IconUser size={18} />
          </ActionIcon>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown miw={200}>
        <Menu.Label>{user?.email ?? 'Signed in'}</Menu.Label>
        <Menu.Item component={RouterLink} to="/profile" leftSection={<IconUserCircle size={14} />}>
          Your account
        </Menu.Item>
        <Menu.Divider />
        <Menu.Item
          color="red"
          leftSection={<IconLogout size={14} />}
          onClick={() => {
            void logout()
            navigate('/')
          }}
        >
          Sign out
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  )
}
