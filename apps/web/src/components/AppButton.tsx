import { Button } from '@mantine/core'
import { IconPlus } from '@tabler/icons-react'
import { Link } from 'react-router-dom'

/**
 * Primary CTA used across the console ("Review a new client"). Renders as a
 * router Link in primary colour with an optional leading icon.
 */
export function AppButton({
  to,
  children,
  icon,
}: {
  to: string
  children: string
  icon?: 'plus' | 'none'
}) {
  return (
    <Button
      component={Link}
      to={to}
      color="clinical"
      size="xs"
      leftSection={icon === 'plus' ? <IconPlus size={16} /> : undefined}
    >
      {children}
    </Button>
  )
}
