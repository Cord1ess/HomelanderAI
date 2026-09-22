import { Badge, Tooltip } from '@mantine/core'

import type { ApplicationStatus } from '../api/client'
import { STATUS_META } from '../status'

/** The status of an application as a chip, with its meaning on hover. */
export function StatusBadge({ status, size = 'sm' }: { status: ApplicationStatus; size?: 'xs' | 'sm' | 'md' }) {
  const meta = STATUS_META[status] ?? { label: status, meaning: '', color: 'gray' }
  return (
    <Tooltip label={meta.meaning} withArrow multiline maw={280} disabled={!meta.meaning}>
      <Badge
        color={meta.color}
        variant="light"
        size={size}
        leftSection={meta.live ? <span className="status-dot" aria-hidden="true" /> : undefined}
      >
        {meta.label}
      </Badge>
    </Tooltip>
  )
}
