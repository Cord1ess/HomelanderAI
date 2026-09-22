import { Paper, Text } from '@mantine/core'

import type { ApplicationStatus } from '../../api/client'

const STAGES = ['Received', 'Reading evidence', 'Scored'] as const

/**
 * Where a not-yet-scored application is, as three stages with the current one
 * breathing. Shown in place of the score while the models run; the screen
 * polls every few seconds and this is replaced the moment a score lands.
 */
export function ScoringProgress({ status }: { status: ApplicationStatus }) {
  const current = status === 'processing' ? 1 : 0
  return (
    <Paper p="md" className="stage-panel" role="status" aria-live="polite">
      <ol className="stage-track">
        {STAGES.map((name, index) => (
          <li
            key={name}
            className="stage-track__step"
            data-reached={index <= current}
            data-current={index === current}
          >
            {name}
          </li>
        ))}
      </ol>
      <Text size="sm" fw={600} mt="sm">
        {current === 0 ? 'Received. The models start in a moment.' : 'The models are reading the evidence now.'}
      </Text>
      <Text size="sm" style={{ color: 'var(--neo-muted)' }}>
        This usually takes under a minute. The screen updates on its own; there is nothing to press.
      </Text>
    </Paper>
  )
}
