import { Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'

import { getTenantSettingsHistory } from '../../api/client'

/**
 * "Last changed by Name on date" for a group of settings, from the change log.
 * Says nothing when the settings have never been changed.
 */
export function LastChanged({ fields }: { fields: string[] }) {
  const { data } = useQuery({
    queryKey: ['tenant-settings-history'],
    queryFn: getTenantSettingsHistory,
    staleTime: 30_000,
  })
  const last = (data ?? []).find((change) => fields.some((f) => f in change.changes))
  if (!last) return null

  const when = new Date(last.changedAt).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
  return (
    <Text size="xs" mt="xs" style={{ color: 'var(--neo-muted)' }}>
      Last changed by {last.actorName ?? 'a removed account'} on {when}.
    </Text>
  )
}
