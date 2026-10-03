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
      'Send an elevated-risk application to a doctor',
      'Ask the client for documents, and move the answer date with a reason',
    ],
    restrictions: [
      'Cannot approve an elevated-risk application until a doctor has checked its results',
      "Sees a client's name and reference; their contact details and test results need the administrator's approval, asked for with a reason",
      'Cannot open analytics or plans and pricing; they are the company owner\'s',
      'Cannot add team members or change company settings',
    ],
  },
  medical_professional: {
    title: 'Doctor',
    shortTitle: 'Doctor',
    color: 'grape',
    description:
      'You check the results on the applications an underwriter sends you, and tell them whether the results are right. The insurance decision stays with the underwriter.',
    scope: [
      'See the patient, the image, the heatmap and the findings on each application sent to you',
      'Send it back to the underwriter with your verdict: the results are correct, or they are wrong',
      'Write to the client directly when something cannot wait, such as telling them to see a doctor now',
    ],
    restrictions: [
      'See only the applications and clients sent to you',
      "A client's contact details need the administrator's approval, asked for with a reason",
      'Cannot decide an application, set a premium, or take applications in',
      'Cannot add team members or change company settings',
    ],
  },
  admin: {
    title: 'Administrator',
    shortTitle: 'Administrator',
    color: 'orange',
    description:
      'You own this company\'s workspace and can do everything in it: an underwriter\'s work, a doctor\'s work, and the company\'s settings.',
    scope: [
      'Add team members and set their role',
      'See every client\'s details, and answer requests from others to see them',
      'Open analytics, and set the plans and their prices',
      'Take applications in and decide any of them, like an underwriter',
      'Check results and write to clients directly, like a doctor',
      'Set the answer date promised to clients, and the risk boundaries',
    ],
    restrictions: [
      'A recorded decision cannot be changed, by anyone',
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
