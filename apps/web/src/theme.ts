import {
  createTheme,
  type MantineColorsTuple,
  type MantineThemeOverride,
} from '@mantine/core'

// Forest green dark palette — tailored for high contrast and clear segment boundaries.
// dark[0] = primary text: pure crisp white (#FFFFFF)
// dark[1] = high-contrast secondary text (#F1F5F9)
// dark[2] = readable icons & subtitles (#CBD5E1)
// dark[3] = dimmed text: clean, legible slate (#94A3B8)
// dark[4] = borders & dividers: visible dividing lines (#2B4436)
// dark[5] = elevated cards / hover states (#193225)
// dark[6] = card / panel background (#13261C) — distinctly elevated from body
// dark[7] = body background (#0B1811)
// dark[8] = header & navbar background (#07120C) — structural dark frame
// dark[9] = deepest base (#030805)
const dark: MantineColorsTuple = [
  '#FFFFFF',  // dark[0] — pure crisp white for maximum legibility
  '#F1F5F9',  // dark[1] — light slate
  '#CBD5E1',  // dark[2] — subtle labels & readable icons
  '#94A3B8',  // dark[3] — clean legible muted text (not muddy green!)
  '#2B4436',  // dark[4] — crisp visible borders & dividers
  '#193225',  // dark[5] — hover states
  '#13261C',  // dark[6] — distinct card / segment background
  '#0B1811',  // dark[7] — body background
  '#07120C',  // dark[8] — header, navbar background
  '#030805',  // dark[9] — deepest base
]

// Forest green & emerald accent colors
const clinical: MantineColorsTuple = [
  '#eafaf0',
  '#c7f3d6',
  '#91e6b3',
  '#51d38c',
  '#28c06f',
  '#16a34a',
  '#15803d',
  '#166534',
  '#14532d',
  '#1C3829',
]

export const theme: MantineThemeOverride = createTheme({
  primaryColor: 'clinical',
  primaryShade: { light: 6, dark: 4 },
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
          backgroundColor: '#13261C',
          borderColor: 'rgba(255, 255, 255, 0.12)',
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.28)',
        },
      },
    },
    Paper: {
      defaultProps: { withBorder: true },
      styles: {
        root: {
          backgroundColor: '#13261C',
          borderColor: 'rgba(255, 255, 255, 0.12)',
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.2)',
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
