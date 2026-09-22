import { Grid, Stack } from '@mantine/core'

import { useAuth } from '../../context/AuthContext'
import { PageHeader } from '../../components/PageHeader'
import type { UserRole } from '../../types/auth'
import { AccountDetailsCard } from './AccountDetailsCard'
import { AppearanceCard } from './AppearanceCard'
import { ProfileHeader } from './ProfileHeader'
import { RoleAuthorityCard } from './RoleAuthorityCard'
import { SecurityCard } from './SecurityCard'

/**
 * Operator Profile & Workspace Authority Screen.
 *
 * Combines account identification, license verification, underwriting authority
 * documentation, and console settings across all authenticated roles.
 */

const ROLE_META: Record<
  UserRole,
  {
    title: string
    shortTitle: string
    color: string
    description: string
    scope: string[]
    restrictions: string[]
  }
> = {
  underwriter: {
    title: 'Underwriter',
    shortTitle: 'Underwriter',
    color: 'clinical',
    description:
      'You take applications in and decide the ones the models put in the low and moderate tiers.',
    scope: [
      'Take a new application: the client\'s details, their cover, their evidence',
      'Confirm what each file is before the models read it',
      'Decide applications in the low and moderate tiers, and set the premium on an adjusted approval',
      'Escalate an elevated-risk application to a medical professional',
      'Ask the client for documents, and move the answer date with a reason',
    ],
    restrictions: [
      'Cannot approve an application the models put in the elevated tier; that needs a medical professional',
      'Cannot add staff or change company settings',
    ],
  },
  medical_professional: {
    title: 'Medical Professional',
    shortTitle: 'Medical Professional',
    color: 'grape',
    description:
      'You read the medical evidence on escalated applications and decide them. Everything an underwriter can do, you can do too.',
    scope: [
      'Decide applications in every tier, including the elevated ones underwriters escalate',
      'See the image, the heatmap and the findings behind every score',
      'Set the premium on an adjusted approval',
      'Take applications in and ask clients for documents, like an underwriter',
    ],
    restrictions: [
      'Cannot add staff or change company settings',
      'A recorded decision cannot be changed, by anyone',
    ],
  },
  admin: {
    title: 'Administrator',
    shortTitle: 'Administrator',
    color: 'orange',
    description:
      'You run this company\'s workspace: who can sign in, and the defaults every application follows.',
    scope: [
      'Add staff and set their role',
      'Set the answer date promised to clients, in working days',
      'See every application and its audit trail',
      'Take applications in, like an underwriter',
    ],
    restrictions: [
      'Cannot decide an application; decisions are recorded by underwriters and medical professionals',
    ],
  },
}

export function ProfilePage() {
  const { user, tenant } = useAuth()
  const roleInfo = user?.role ? ROLE_META[user.role] : ROLE_META.underwriter

  return (
    <Stack gap="lg">
      <PageHeader screen="profile" />
      <ProfileHeader
        user={user}
        tenant={tenant}
        roleTitle={roleInfo.title}
        roleShortTitle={roleInfo.shortTitle}
        roleColor={roleInfo.color}
      />

      <Grid>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Stack gap="md">
            <AccountDetailsCard user={user} tenant={tenant} roleTitle={roleInfo.title} />
            <RoleAuthorityCard roleInfo={roleInfo} />
          </Stack>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 5 }}>
          <Stack gap="md">
            <AppearanceCard />
            <SecurityCard />
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
