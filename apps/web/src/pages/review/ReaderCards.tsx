import { Badge, Group, Paper, SimpleGrid, Text, UnstyledButton } from '@mantine/core'

import type { ArmRun } from '../../api/client'
import { bandFor, headlineOf, infoFor, type Limits } from './readers'

/**
 * One card per reader: its score, its band against the company's boundaries,
 * and what it concluded in a few words. Selecting a card is the caller's
 * business — the result page opens that reader's tab, the client profile
 * opens the result page on it.
 */
export function ReaderCards({
  groups,
  limits,
  active,
  onSelect,
}: {
  groups: { arm: string; runs: ArmRun[] }[]
  limits: Limits
  active?: string | null
  onSelect: (arm: string) => void
}) {
  return (
    <SimpleGrid cols={{ base: 1, xs: 2, md: 3 }} spacing="sm">
      {groups.map((g) => {
        const info = infoFor(g.arm)
        const run = g.runs[0]
        const band = bandFor(run.score, limits)
        const Icon = info.icon
        const selected = g.arm === active
        return (
          <UnstyledButton
            key={g.arm}
            onClick={() => onSelect(g.arm)}
            aria-pressed={active === undefined ? undefined : selected}
            aria-label={`Open the ${info.title} reading`}
          >
            <Paper
              p="sm"
              h="100%"
              bd={
                selected
                  ? '2px solid var(--mantine-primary-color-filled)'
                  : '1px solid var(--mantine-color-default-border)'
              }
              style={{ transition: 'border-color 120ms ease' }}
            >
              <Group justify="space-between" wrap="nowrap" mb={6}>
                <Group gap={6} wrap="nowrap">
                  <Icon size={16} />
                  <Text size="sm" fw={600}>
                    {info.title}
                  </Text>
                </Group>
                {band && (
                  <Badge size="xs" variant="light" color={band.color}>
                    {band.label}
                  </Badge>
                )}
              </Group>
              <Group gap={6} align="baseline" wrap="nowrap">
                <Text fw={700} size="xl" ff="monospace">
                  {run.score != null ? run.score.toFixed(1) : '—'}
                </Text>
                {g.runs.length > 1 && (
                  <Text size="xs" c="dimmed">
                    +{g.runs.length - 1} more
                  </Text>
                )}
              </Group>
              <Text size="xs" c={run.error ? 'yellow.7' : 'dimmed'} lineClamp={2}>
                {headlineOf(run, limits)}
              </Text>
            </Paper>
          </UnstyledButton>
        )
      })}
    </SimpleGrid>
  )
}
