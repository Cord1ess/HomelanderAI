import { ActionIcon, Tooltip, useComputedColorScheme, useMantineColorScheme } from '@mantine/core'
import { IconMoon, IconSun } from '@tabler/icons-react'

/**
 * Light or dark, one button, used on every surface: landing page, sign-in,
 * portal and console header.
 *
 * The console follows the operating system until this is pressed; after that
 * the choice is remembered (Mantine stores it in localStorage and index.html
 * reads it before first paint). The icon shows what you will get, not what you
 * have: a sun in the dark, a moon in the light.
 */
export function ThemeToggle({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const { setColorScheme } = useMantineColorScheme()
  // "auto" resolves to whichever the device is using right now.
  const current = useComputedColorScheme('light')
  const next = current === 'dark' ? 'light' : 'dark'

  return (
    <Tooltip label={next === 'dark' ? 'Switch to dark' : 'Switch to light'} withArrow>
      <ActionIcon
        variant="subtle"
        size={size}
        aria-label={next === 'dark' ? 'Switch to dark mode' : 'Switch to light mode'}
        onClick={() => setColorScheme(next)}
        style={{ color: 'var(--neo-ink-2)' }}
      >
        {current === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
      </ActionIcon>
    </Tooltip>
  )
}
