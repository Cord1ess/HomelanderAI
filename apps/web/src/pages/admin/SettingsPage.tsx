import { SimpleGrid, Stack } from '@mantine/core'

import { PageHeader } from '../../components/PageHeader'
import { CompanyCard } from './CompanyCard'
import { MailCard } from './MailCard'
import { PricingPolicyCard } from './PricingPolicyCard'
import { ThresholdsCard } from './ThresholdsCard'
import { TurnaroundCard } from './TurnaroundCard'

/**
 * Company settings: the defaults an administrator sets once for every
 * application the company takes. Each card is one setting, says what it
 * changes and what it does not, and saves on its own.
 *
 * The company's name, outgoing email, the answer date promised to clients,
 * the risk-score boundaries, and the pricing policy. Every change is recorded with who made
 * it, and none rewrites the past: dates already promised and scores already
 * computed keep what they had.
 */
export function SettingsPage() {
  return (
    <Stack gap="lg" maw={1080}>
      <PageHeader screen="settings" />
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        <CompanyCard />
        <MailCard />
        <ThresholdsCard />
        <PricingPolicyCard />
        <TurnaroundCard />
      </SimpleGrid>
    </Stack>
  )
}
