import {
  createTheme,
  type CSSVariablesResolver,
  type MantineColorsTuple,
  type MantineThemeOverride,
} from '@mantine/core'

import { DARK, DARK_RAMP, LIGHT, MOTION, OLIVE_RAMP, type SchemeTokens } from './tokens'

/**
 * The Mantine theme, built from src/tokens.ts.
 *
 * Two things happen here. The tokens become CSS variables for each colour
 * scheme (`--neo-*`, read by the public pages, the sign-in pages and the
 * portal), and Mantine's own variables are pointed at the same values, so a
 * Card, a Table or a Button in the console lands on the same surface colours
 * as everything else. One set of numbers, two ways in.
 *
 * Nothing in this file names a colour. If a hex is needed, it belongs in
 * tokens.ts, where the contrast script can see it.
 */

// `clinical` is the historical name of the accent ramp and is used by colour
// props across the console (color="clinical"). Kept as the Mantine name; the
// ramp itself lives in tokens.ts.
const clinical: MantineColorsTuple = [...OLIVE_RAMP]
const dark: MantineColorsTuple = [...DARK_RAMP]

/** The `--neo-*` variables one scheme's tokens produce. */
function neoVariables(t: SchemeTokens): Record<string, string> {
  return {
    '--neo-bg': t.bg,
    '--neo-card': t.card,
    '--neo-raised': t.raised,
    '--neo-hover': t.hover,
    '--neo-ink': t.ink,
    '--neo-ink-2': t.ink2,
    '--neo-muted': t.muted,
    '--neo-border': t.border,
    '--neo-border-mid': t.borderMid,
    '--neo-border-strong': t.borderStrong,
    '--neo-accent': t.accent,
    '--neo-accent-deep': t.accentDeep,
    '--neo-accent-soft': t.accentSoft,
    '--neo-accent-ink': t.accentInk,
    '--neo-forest': t.forest,
    '--neo-forest-mid': t.forestMid,
    '--neo-forest-soft': t.forestSoft,
    '--neo-forest-ink': t.forestInk,
    '--neo-shadow': t.shadow,
    '--neo-ok': t.ok,
    '--neo-warn': t.warn,
    '--neo-danger': t.danger,
    '--neo-info': t.info,
    '--neo-ok-soft': t.okSoft,
    '--neo-warn-soft': t.warnSoft,
    '--neo-danger-soft': t.dangerSoft,
    '--neo-info-soft': t.infoSoft,
  }
}

/** Mantine's own variables, pointed at the same tokens. */
function mantineVariables(t: SchemeTokens): Record<string, string> {
  return {
    '--mantine-color-body': t.bg,
    '--mantine-color-text': t.ink,
    '--mantine-color-bright': t.ink,
    '--mantine-color-dimmed': t.muted,
    '--mantine-color-placeholder': t.muted,
    '--mantine-color-anchor': t.accent,
    '--mantine-color-default': t.card,
    '--mantine-color-default-hover': t.hover,
    '--mantine-color-default-color': t.ink,
    '--mantine-color-default-border': t.borderMid,
    '--mantine-color-error': t.danger,
  }
}

export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {
    '--motion-fast': MOTION.fast,
    '--motion-base': MOTION.base,
    '--motion-slow': MOTION.slow,
    '--ease-out': MOTION.easeOut,
    '--ease-in-out': MOTION.easeInOut,
  },
  light: { ...neoVariables(LIGHT), ...mantineVariables(LIGHT) },
  dark: { ...neoVariables(DARK), ...mantineVariables(DARK) },
})

export const theme: MantineThemeOverride = createTheme({
  primaryColor: 'clinical',
  // The ramp is split by scheme (see tokens.ts): clinical[3] is solved against
  // the dark card, clinical[6] against the light page.
  primaryShade: { light: 6, dark: 3 },
  colors: { clinical, dark },

  // Honour the operating system's reduced-motion setting in Mantine's own
  // transitions; index.css does the same for ours.
  respectReducedMotion: true,

  // Denser spacing/radius for an information-dense underwriting console.
  defaultRadius: 'sm',
  spacing: {
    xs: '0.25rem',
    sm: '0.5rem',
    md: '0.75rem',
    lg: '1rem',
    xl: '1.5rem',
  },
  fontSizes: {
    xs: '0.7rem',
    sm: '0.8rem',
    md: '0.875rem',
    lg: '1rem',
    xl: '1.125rem',
  },

  // Space Grotesk Variable, one font for the entire product.
  fontFamily:
    '"Space Grotesk Variable", "Space Grotesk", Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif',
  fontFamilyMonospace:
    'ui-monospace, "JetBrains Mono", "Cascadia Code", Menlo, Consolas, monospace',

  headings: {
    fontFamily:
      '"Space Grotesk Variable", "Space Grotesk", Inter, ui-sans-serif, sans-serif',
    fontWeight: '600',
    sizes: {
      h1: { fontSize: '1.125rem', lineHeight: '1.4' },
      h2: { fontSize: '1rem', lineHeight: '1.4' },
      h3: { fontSize: '0.875rem', lineHeight: '1.4' },
    },
  },

  components: {
    Card: {
      defaultProps: { withBorder: true, padding: 'md' },
      styles: {
        root: {
          backgroundColor: 'var(--neo-card)',
          borderColor: 'var(--neo-border-mid)',
          boxShadow: '0 4px 20px var(--neo-shadow)',
        },
      },
    },
    Paper: {
      defaultProps: { withBorder: true },
      styles: {
        root: {
          backgroundColor: 'var(--neo-card)',
          borderColor: 'var(--neo-border-mid)',
          boxShadow: '0 4px 16px var(--neo-shadow)',
        },
      },
    },
    Table: {
      defaultProps: {
        horizontalSpacing: 'sm',
        verticalSpacing: 'sm',
        fz: 'sm',
        highlightOnHover: true,
      },
    },
    Button: {
      defaultProps: { size: 'xs' },
      styles: {
        // The primary fill is a light olive on dark and a mid olive on light.
        // Mantine puts white text on a filled button by default, which is
        // invisible on the light olive. The token knows which ink reads on the
        // fill in each scheme, so the label follows it.
        //
        // Only `filled`; subtle/light/outline variants draw their label from
        // the accent itself and are already correct.
        root: {
          '&[data-variant="filled"]': {
            color: 'var(--neo-accent-ink)',
          },
        },
      },
    },
    ActionIcon: {
      defaultProps: { variant: 'subtle', size: 'md' },
    },
    TextInput: {
      defaultProps: { size: 'xs' },
    },
    NumberInput: {
      defaultProps: { size: 'xs' },
    },
    Select: {
      defaultProps: { size: 'xs' },
    },
    Textarea: {
      defaultProps: { size: 'xs' },
    },
    Title: {
      defaultProps: { order: 1 },
      styles: {
        root: {
          color: 'var(--neo-ink)',
        },
      },
    },
  },
})
