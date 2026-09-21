import { Badge } from '@mantine/core'

// Mirrors the risk_tier enum in db/schema.sql.
type Tier = 'low' | 'moderate' | 'elevated' | 'insufficient_evidence'

const TIER_META: Record<Tier, { label: string; color: string }> = {
  low: { label: 'Low', color: 'teal' },
  moderate: { label: 'Moderate', color: 'yellow' },
  elevated: { label: 'Elevated', color: 'red' },
  insufficient_evidence: { label: 'Insufficient', color: 'gray' },
}

/**
 * Risk tier chip, matching the spec colour map:
 * low teal · moderate yellow · elevated red · insufficient_evidence gray.
 *
 * These stay OUT of the olive brand palette on purpose. They are a traffic
 * light, not decoration, and the brand is yellow-green — an olive "low" next to
 * a yellow "moderate" would be nearly the same hue, on the one chip an
 * underwriter reads fastest. Keeping status colours independent of the accent
 * also means a future rebrand cannot quietly make two risk levels look alike.
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
