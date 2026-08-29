import { createTheme, type MantineColorsTuple } from '@mantine/core'

// A desaturated clinical teal rather than the default indigo — this app sits
// next to medical imagery, so the chrome should stay quiet and let heatmap
// overlays carry the colour.
const clinical: MantineColorsTuple = [
  '#eaf6f5',
  '#d6e8e7',
  '#aed1cf',
  '#83b9b6',
  '#61a5a1',
  '#4b9995',
  '#3d938e',
  '#2d7f7b',
  '#1f716d',
  '#06625e',
]

// Reserved for risk tiers so they read consistently everywhere they appear.
const tier: MantineColorsTuple = [
  '#fff4e2',
  '#ffe9cc',
  '#fed09b',
  '#fdb564',
  '#fc9e38',
  '#fc911c',
  '#fc8a0c',
  '#e17600',
  '#c86800',
  '#ae5800',
]

export const theme = createTheme({
  primaryColor: 'clinical',
  primaryShade: { light: 7, dark: 5 },
  colors: { clinical, tier },

  defaultRadius: 'sm',

  fontFamily:
    'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  fontFamilyMonospace:
    'ui-monospace, "JetBrains Mono", "Cascadia Code", Menlo, Consolas, monospace',

  headings: {
    fontWeight: '600',
    sizes: {
      h1: { fontSize: '1.75rem', lineHeight: '1.25' },
      h2: { fontSize: '1.35rem', lineHeight: '1.3' },
    },
  },

  components: {
    Card: {
      defaultProps: { withBorder: true, padding: 'lg' },
    },
    Badge: {
      defaultProps: { variant: 'light' },
    },
  },
})
