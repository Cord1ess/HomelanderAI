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
      'Adjudication & rate adjustment for Tier 1 (score up to 30) & Tier 2 (score above 30, up to 65)',
      'Direct escalation routing to a Medical Professional for Tier 3 cases',
      'Requesting supplementary clinical documentation from applicants',
    ],
    restrictions: [
      'Binding approval prohibited on Tier 3 (Elevated Risk) cases without Medical Professional sign-off',
      'Cannot edit or delete carrier-level underwriting policy guidelines',
      'Cannot provision or deactivate colleague accounts (Administrator exclusive)',
    ],
  },
  medical_professional: {
    title: 'Medical Professional',
    shortTitle: 'Medical Professional',
    color: 'grape',
    description:
      'Clinical review authority for this carrier: reads the medical evidence on escalated applications and decides the Tier 3 (Elevated Risk) cases an underwriter may not.',
    scope: [
      'Full adjudication discretion across all risk tiers (Tier 1, Tier 2, Tier 3)',
      'Mandatory review and binding sign-off on escalated high-risk applications',
      'Detailed inspection of 18-finding vision probability & Grad-CAM explainability heatmaps',
      'Application of customized actuarial rate surcharges and final premium binding',
      'Queue monitoring and review backlog prioritization within this carrier',
    ],
    restrictions: [
      'Cannot provision staff or change carrier settings (Administrator exclusive)',
      'Adjudication decisions are write-once per regulatory compliance audit trail',
    ],
  },
  admin: {
    title: 'Carrier Administrator',
    shortTitle: 'Administrator',
    color: 'orange',
    description:
      'Runs this carrier workspace: staff accounts, carrier settings such as the turnaround promise, and audit trail inspection.',
    scope: [
      'Carrier settings, including the working-day turnaround promised to applicants',
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
