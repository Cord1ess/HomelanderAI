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
  IconChevronsLeft,
  IconChevronsRight,
  IconFilePlus,
  IconFlame,
  IconLayoutDashboard,
  IconLogout,
  IconReceipt,
  IconShieldCheck,
  IconStethoscope,
  IconUser,
  IconUserCircle,
  IconUsers,
} from '@tabler/icons-react'
import type { JSX } from 'react'
import { NavLink as RouterLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { getNotifications } from '../../api/client'
import { BrandIcon } from '../../components/BrandIcon'
import { ThemeToggle } from '../../components/ThemeToggle'
import { useAuth } from '../../context/AuthContext'
import { ROLE_LABEL } from '../../types/auth'
import type { UserRole } from '../../types/auth'

/**
 * ERP-style shell for the authenticated dashboard.
 *
 * Role-aware: renders dedicated workspaces, customized navbars, and distinct
 * privilege badges for the three roles: Underwriter, Medical Professional and Administrator.
 */
export function AppLayout() {
  const { user } = useAuth()
  const [navOpened, { toggle: toggleNav }] = useDisclosure(true)
  const [mobileOpened, { toggle: toggleMobile }] = useDisclosure(false)
  const location = useLocation()

  const role = user?.role ?? 'underwriter'
  const title = routeFor(location.pathname, role)?.title
  const navItems = getNavForRole(role)

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
        width: navOpened ? 240 : 56,
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
            <Badge color={ROLE_COLOR[role]} variant="filled" size="xs">
              {ROLE_LABEL[role]}
            </Badge>
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
            <ThemeToggle />
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
              backgroundColor: '#fff', // the mark is drawn for a white disc
              border: '1px solid var(--neo-border-mid)',
              boxShadow: '0 2px 10px var(--neo-shadow)',
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
          {navItems.map((item) => (
            <NavItem
              key={item.to}
              to={item.to}
              label={item.label}
              icon={item.icon}
              collapsed={!navOpened}
              active={location.pathname === item.to || (item.to !== '/queue' && location.pathname.startsWith(item.to))}
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

/** Badge colour per role. The name comes from ROLE_LABEL, shared with every other screen. */
const ROLE_COLOR: Record<UserRole, string> = {
  underwriter: 'clinical',
  medical_professional: 'grape',
  admin: 'orange',
}

function getNavForRole(role?: UserRole): { to: string; label: string; icon: () => JSX.Element }[] {
  if (role === 'medical_professional') {
    return [
      { to: '/escalations', label: 'Escalations', icon: () => <IconFlame size={18} /> },
      { to: '/queue', label: 'Clinical queue', icon: () => <IconStethoscope size={18} /> },
      { to: '/applications/new', label: 'New applicant intake', icon: () => <IconFilePlus size={18} /> },
      { to: '/pricing', label: 'Risk bands', icon: () => <IconReceipt size={18} /> },
      { to: '/notifications', label: 'Notifications', icon: () => <IconBell size={18} /> },
      { to: '/profile', label: 'My profile', icon: () => <IconUserCircle size={18} /> },
    ]
  }

  if (role === 'admin') {
    return [
      { to: '/admin/users', label: 'Staff governance', icon: () => <IconUsers size={18} /> },
      { to: '/queue', label: 'Carrier audit', icon: () => <IconShieldCheck size={18} /> },
      { to: '/applications/new', label: 'New applicant intake', icon: () => <IconFilePlus size={18} /> },
      { to: '/pricing', label: 'Policy pricing', icon: () => <IconReceipt size={18} /> },
      { to: '/notifications', label: 'Notifications', icon: () => <IconBell size={18} /> },
      { to: '/profile', label: 'My profile', icon: () => <IconUserCircle size={18} /> },
    ]
  }

  // default: underwriter
  return [
    { to: '/queue', label: 'Intake queue', icon: () => <IconLayoutDashboard size={18} /> },
    { to: '/applications/new', label: 'New applicant intake', icon: () => <IconFilePlus size={18} /> },
    { to: '/pricing', label: 'Plan rate card', icon: () => <IconReceipt size={18} /> },
    { to: '/notifications', label: 'Notifications', icon: () => <IconBell size={18} /> },
    { to: '/profile', label: 'My profile', icon: () => <IconUserCircle size={18} /> },
  ]
}

function routeFor(path: string, role?: UserRole) {
  if (path === '/escalations') return { title: 'Escalation Command Center' }
  if (path === '/admin/users') return { title: 'Carrier Staff & Access Governance' }
  if (path === '/queue') {
    if (role === 'medical_professional') return { title: 'Clinical Review Queue' }
    if (role === 'admin') return { title: 'Carrier Submission Audit' }
    return { title: 'Underwriting Intake Queue' }
  }
  if (path.startsWith('/applications/new')) return { title: 'New Applicant Intake Form' }
  if (path.startsWith('/applications/')) return { title: 'Underwriting Adjudication' }
  if (path.startsWith('/notifications')) return { title: 'Notifications' }
  if (path.startsWith('/pricing')) return { title: 'Plan & Risk Structure' }
  if (path.startsWith('/profile')) return { title: 'Operator Profile & Authority' }
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
        size={22}
        radius="sm"
        style={
          active
            ? {
                backgroundColor: 'var(--neo-forest)',
                color: 'var(--neo-forest-ink)',
              }
            : {
                color: 'var(--neo-muted)',
              }
        }
      >
        {icon()}
      </ThemeIcon>
      {!collapsed && (
        <span
          style={{
            fontWeight: active ? 700 : 500,
            fontSize: '0.825rem',
          }}
        >
          {label}
        </span>
      )}
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
  const { user, logout } = useAuth()
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
        <Menu.Item leftSection={<IconUser size={14} />}>
          {user?.email ?? 'unknown'}
        </Menu.Item>
        <Menu.Item
          component={RouterLink}
          to="/profile"
          leftSection={<IconUserCircle size={14} />}
        >
          Profile & workspace
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
