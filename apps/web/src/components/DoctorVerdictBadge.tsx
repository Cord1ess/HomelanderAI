import { Badge } from '@mantine/core'

/**
 * The tag a doctor's review leaves on an application's results. Shown wherever
 * the application is: the result page, the queue, the client's profile and the
 * doctor's own list.
 */
export function DoctorVerdictBadge({
  verdict,
  size = 'sm',
}: {
  verdict: string | null | undefined
  size?: 'xs' | 'sm' | 'md'
}) {
  if (verdict !== 'accurate' && verdict !== 'inaccurate') return null
  return (
    <Badge
      size={size}
      variant="light"
      color={verdict === 'accurate' ? 'teal' : 'red'}
      style={{ minWidth: 'max-content' }}
    >
      {verdict === 'accurate' ? 'Doctor verified: correct' : 'Doctor verified: wrong'}
    </Badge>
  )
}
