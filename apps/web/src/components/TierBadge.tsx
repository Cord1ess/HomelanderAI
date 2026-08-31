import { Badge } from '@mantine/core'

type Tier = 'low' | 'moderate' | 'elevated' | 'insufficient'

const TIER_META: Record<Tier, { label: string; color: string }> = {
  low: { label: 'Low', color: 'teal' },
  moderate: { label: 'Moderate', color: 'yellow' },
  elevated: { label: 'Elevated', color: 'red' },
  insufficient: { label: 'Insufficient', color: 'gray' },
}

/**
 * Risk tier chip, matching the spec colour map:
 * low teal · moderate yellow · elevated red · insufficient gray.
 */
export function TierBadge({ tier }: { tier: Tier }) {
  const meta = TIER_META[tier]
  return (
    <Badge color={meta.color} variant="light" size="sm">
      {meta.label}
    </Badge>
  )
}

export type { Tier }
export { TIER_META }
