import { Avatar, Badge, Group, Paper, Text, Tooltip } from '@mantine/core'

import type { Tenant, User } from '../../types/auth'

interface ProfileHeaderProps {
  user: User | null
  tenant: Tenant | null
  roleTitle: string
  roleShortTitle: string
  roleColor: string
}

export function ProfileHeader({
  user,
  tenant,
  roleShortTitle,
  roleColor,
}: ProfileHeaderProps) {
  const initials = user?.fullName
    ? user.fullName
        .split(' ')
        .map((n) => n[0])
        .slice(0, 2)
        .join('')
        .toUpperCase()
    : 'UW'

  return (
    <Paper
      p="lg"
      bd="1px solid var(--mantine-color-default-border)"
      style={{
        background: 'linear-gradient(135deg, var(--neo-accent-soft) 0%, var(--neo-card) 100%)',
        borderRadius: 'var(--mantine-radius-md)',
      }}
    >
      <Group justify="space-between" align="center" wrap="wrap">
        <Group gap="md">
          <Avatar
            size={56}
            radius="xl"
            color={roleColor}
            style={{
              fontSize: '1.25rem',
              fontWeight: 700,
              border: '2px solid var(--neo-border-mid)',
            }}
          >
            {initials}
          </Avatar>
          <div>
            <Group gap="xs" align="center">
              <Text fw={700} size="lg">
                {user?.fullName ?? 'Underwriting Officer'}
              </Text>
              <Badge color={roleColor} variant="filled" size="sm">
                {roleShortTitle}
              </Badge>
            </Group>
            <Text size="xs" c="dimmed" mt={2}>
              {user?.email} · {tenant?.name ?? 'Homelander Assurance Ltd.'}
            </Text>
          </div>
        </Group>

        <Group gap="xs">
          <Tooltip label="Multi-tenant cryptographic data boundary active" withArrow>
            <Badge variant="outline" color="gray" size="md">
              Carrier: {tenant?.name ?? 'Demo Carrier'}
            </Badge>
          </Tooltip>
          <Badge variant="dot" color="teal" size="md">
            Active Session
          </Badge>
        </Group>
      </Group>
    </Paper>
  )
}
