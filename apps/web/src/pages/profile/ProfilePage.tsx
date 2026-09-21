import { Grid, Stack } from '@mantine/core'

import { useAuth } from '../../context/AuthContext'
import type { UserRole } from '../../types/auth'
import { AccountDetailsCard } from './AccountDetailsCard'
import { ConsolePreferencesCard } from './ConsolePreferencesCard'
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
    title: 'Licensed Medical Underwriter',
    shortTitle: 'Underwriter',
    color: 'clinical',
    description:
      'Primary operator responsible for intake interviews, evidence ingestion, and adjudication of Tier 1 (Low) and Tier 2 (Moderate) applications.',
    scope: [
      'Client intake interviews and structured questionnaire recording',
      'Evidence attachment and model arm specification (Chest X-ray / DenseNet)',
      'Adjudication & rate adjustment for Tier 1 (CRS < 25) & Tier 2 (CRS 25–50)',
      'Direct escalation routing to Senior Underwriter for Tier 3 cases',
      'Requesting supplementary clinical documentation from applicants',
    ],
    restrictions: [
      'Binding approval prohibited on Tier 3 (Elevated Risk) cases without Senior sign-off',
      'Cannot edit or delete carrier-level underwriting policy guidelines',
      'Cannot provision or deactivate colleague accounts (Admin exclusive)',
    ],
  },
  senior_underwriter: {
    title: 'Senior Underwriter / Medical Officer',
    shortTitle: 'Senior Underwriter',
    color: 'grape',
    description:
      'Chief underwriting review authority overseeing all tenant applications, complex clinical triages, and mandatory adjudication of Tier 3 (Elevated Risk) escalated cases.',
    scope: [
      'Full adjudication discretion across all risk tiers (Tier 1, Tier 2, Tier 3)',
      'Mandatory review and binding sign-off on escalated high-risk applications',
      'Detailed inspection of 18-finding vision probability & Grad-CAM explainability heatmaps',
      'Application of customized actuarial rate surcharges and final premium binding',
      'Cross-tenant queue monitoring and review backlog prioritization',
    ],
    restrictions: [
      'Cannot provision or delete carrier tenant configuration (Admin exclusive)',
      'Adjudication decisions are write-once per regulatory compliance audit trail',
    ],
  },
  admin: {
    title: 'Carrier System Administrator',
    shortTitle: 'Administrator',
    color: 'orange',
    description:
      'Organization administrator managing carrier tenant settings, staff account access governance, and compliance audit trail inspection.',
    scope: [
      'Carrier tenant provisioning and subscription tier administration',
      'User management: creating, onboarding, and deactivating operator accounts',
      'Audit log inspection and compliance verification across all submissions',
      'Underwriting workflow operational health monitoring',
    ],
    restrictions: [
      'Does not perform routine medical intake or clinical score adjudication',
    ],
  },
}

export function ProfilePage() {
  const { user, tenant } = useAuth()
  const roleInfo = user?.role ? ROLE_META[user.role] : ROLE_META.underwriter

  return (
    <Stack gap="lg">
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
            <ConsolePreferencesCard />
            <SecurityCard />
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
