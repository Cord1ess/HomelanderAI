import {
  createTheme,
  type MantineColorsTuple,
  type MantineThemeOverride,
} from '@mantine/core'

// ── Brand ────────────────────────────────────────────────────────────────────
//
// The identity is a **hue**, not three fixed hex values: yellow-green at ~68.5°,
// which is where all three reference colours sit (#3D4127, #636B2F, #D4DE95 are
// hue 69.2 / 68.0 / 68.2). Hue and saturation carry the brand; lightness is the
// free variable, because lightness is what contrast is made of.
//
// So every value below was *solved* rather than picked: given a surface and a
// contrast target, find the lightness in our hue that just clears it. That is
// why numbers look arbitrary — they are the point at which a requirement is
// met. Nudging one by eye silently breaks the guarantee it was chosen for.
export const BRAND_HUE = 68.5

// Reference colours, kept for documentation. The ramp reproduces the family,
// and clinical[8] lands on #3D4127 exactly; the other two are close relatives
// at the lightness their role actually needs.
export const BRAND = {
  darkOlive: '#3D4127',
  olive: '#636B2F',
  lightGreen: '#D4DE95',
} as const

// Olive shell — neutrals warmed into the brand hue rather than left blue-grey,
// so panels sit in the same family as the accent instead of fighting it.
// Ratios below are against dark[7], the body background.
const dark: MantineColorsTuple = [
  '#FFFFFF',  // dark[0] primary text      19.37:1
  '#EEEFEB',  // dark[1] secondary text    16.77:1
  '#B0B39A',  // dark[2] icons & subtitles  9.01:1
  '#878C66',  // dark[3] dimmed text        5.51:1 — headroom over the 4.5 floor
  '#40432D',  // dark[4] borders & dividers (1.63:1 on a card — visible edge)
  '#2A2C21',  // dark[5] hover states
  '#1E1F16',  // dark[6] card / panel       1.17:1 over body — panels read apart
  '#0D0E09',  // dark[7] body background
  '#090906',  // dark[8] header & navbar
  '#040503',  // dark[9] deepest base
]

// Accent ramp. Split by scheme rather than running light-to-dark throughout:
// steps 0-5 are solved against the dark card, steps 6-9 against the light page
// background. Each one exists to hit a specific threshold.
const clinical: MantineColorsTuple = [
  '#FAFCF3',  // clinical[0] 16.06:1 on dark — highest emphasis
  '#EFF3D8',  // clinical[1] 14.64:1 on dark
  '#CED98C',  // clinical[2] 11.03:1 on dark — key figures, active nav
  '#A0B13E',  // clinical[3]  7.01:1 on dark — PRIMARY on dark surfaces
  '#7F8C34',  // clinical[4]  4.52:1 on dark — the floor for body text
  '#646E2B',  // clinical[5]  3.01:1 on dark — boundaries and large text only
  '#6D7826',  // clinical[6]  4.54:1 on light — PRIMARY on light surfaces
  '#515A1E',  // clinical[7]  7.01:1 on light — emphasis on light
  '#3D4127',  // clinical[8] 10.00:1 on light — structural dark olive
  '#212315',  // clinical[9] 15.07:1 on light — deepest ink
]

export const theme: MantineThemeOverride = createTheme({
  primaryColor: 'clinical',
  // The ramp is split by scheme, so the two halves take different steps:
  // clinical[3] is solved against the dark card (7.01:1), clinical[6] against
  // the light page (4.54:1). A single shade cannot serve both — the lightness
  // that reads on near-black is the one that vanishes on near-white.
  primaryShade: { light: 6, dark: 3 },
  colors: { clinical, dark },

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

  // Space Grotesk Variable — single font for the entire product.
  fontFamily:
    '"Space Grotesk Variable", "Space Grotesk", Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif',
  fontFamilyMonospace:
    'ui-monospace, "JetBrains Mono", "Cascadia Code", Menlo, Consolas, monospace',

  headings: {
    // Space Grotesk for all headings — consistent with body.
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
          backgroundColor: 'var(--mantine-color-dark-6)',
          borderColor: 'var(--mantine-color-dark-4)',
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.32)',
        },
      },
    },
    Paper: {
      defaultProps: { withBorder: true },
      styles: {
        root: {
          backgroundColor: 'var(--mantine-color-dark-6)',
          borderColor: 'var(--mantine-color-dark-4)',
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.24)',
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
        // The dark scheme's primary is clinical[3] #A0B13E — a LIGHT olive,
        // because that is what reads on a near-black card. Mantine puts white
        // label text on a filled button by default, which would be 2.37:1 on
        // this fill and effectively invisible. Dark ink on it is 8.17:1.
        //
        // This only applies to `filled`; subtle/light/outline variants draw
        // their label from the accent itself and are already correct.
        root: {
          '&[data-variant="filled"]': {
            color: 'var(--mantine-color-dark-7)',
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
          color: '#FFFFFF',
        },
      },
    },
  },
})
