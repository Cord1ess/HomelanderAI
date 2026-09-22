import { Card, Text } from '@mantine/core'

/**
 * One number with its name and, when the name alone would not do, a line
 * saying what it counts. Used in the summary strips under screen headers.
 *
 * `color` is a Mantine colour name for the figure; leave it for a neutral
 * count. Only real counts belong here: a figure that cannot go down is not a
 * statistic, it is decoration.
 */
export function Stat({
  label,
  value,
  hint,
  color,
}: {
  label: string
  value: number | string
  hint?: string
  color?: string
}) {
  return (
    <Card p="sm" className="stat">
      <Text size="xs" fw={600} style={{ color: 'var(--neo-muted)' }}>
        {label}
      </Text>
      <Text fz="1.4rem" fw={700} lh={1.2} c={color} className="stat__value">
        {value}
      </Text>
      {hint && (
        <Text size="xs" mt={2} style={{ color: 'var(--neo-muted)' }}>
          {hint}
        </Text>
      )}
    </Card>
  )
}
