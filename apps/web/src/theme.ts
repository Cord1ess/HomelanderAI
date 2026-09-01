import {
  createTheme,
  type MantineColorsTuple,
  type MantineThemeOverride,
} from '@mantine/core'

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

export const theme: MantineThemeOverride = createTheme({
  primaryColor: 'clinical',
  primaryShade: { light: 7, dark: 5 },
  colors: { clinical },

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

  fontFamily:
    'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  fontFamilyMonospace:
    'ui-monospace, "JetBrains Mono", "Cascadia Code", Menlo, Consolas, monospace',

  headings: {
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
    },
    Badge: {
      defaultProps: { variant: 'light' },
    },
    Table: {
      defaultProps: {
        horizontalSpacing: 'sm',
        verticalSpacing: 'sm',
        fz: 'sm',
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
    },
  },
})
