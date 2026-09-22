/**
 * Design tokens. The one place a colour or a duration is decided.
 *
 * Everything else reads these: the Mantine theme (theme.ts) turns them into
 * CSS variables for both colour schemes, the landing page, the sign-in pages,
 * the client portal and the console all use those variables, and
 * `scripts/contrast.mjs` checks every text-on-surface pairing below against
 * WCAG AA (4.5:1) so a change here cannot quietly make something unreadable.
 *
 * No imports, on purpose: the script runs this file directly under Node.
 *
 * The identity is a hue, not fixed hexes: yellow-green at ~68.5 degrees, where
 * the three reference colours sit (#3D4127, #636B2F, #D4DE95). Lightness is
 * what contrast is made of, so every value was solved against the surface it
 * sits on rather than picked by eye. Nudging one silently breaks the guarantee
 * it was chosen for; the contrast script is what notices.
 */

export const BRAND_HUE = 68.5

export const BRAND = {
  darkOlive: '#3D4127',
  olive: '#636B2F',
  lightGreen: '#D4DE95',
} as const

/** The semantic roles every surface is built from. Same names in both schemes. */
export interface SchemeTokens {
  /** Page background. */
  bg: string
  /** Cards, panels, inputs. */
  card: string
  /** Header and sidebar: the band the console hangs off. */
  raised: string
  /** Hover on a card or row. */
  hover: string

  /** Body text. */
  ink: string
  /** Secondary text: labels, subtitles. */
  ink2: string
  /** Dimmed text: hints, timestamps, placeholders. Still at least 4.5:1. */
  muted: string

  /** Hairline dividers. */
  border: string
  /** Card and input edges. */
  borderMid: string
  /** Emphasised edges: focus rings, selected rows. */
  borderStrong: string

  /** Interactive colour: links, primary buttons, active states. */
  accent: string
  /** Accent with more emphasis: small text, key figures. */
  accentDeep: string
  /** A tint of the accent for backgrounds. */
  accentSoft: string
  /** Text placed on an accent fill. */
  accentInk: string

  /** Structural brand colour: headings on the public pages, the hero button. */
  forest: string
  forestMid: string
  forestSoft: string
  /** Text placed on a forest fill. */
  forestInk: string

  shadow: string

  /** Status colours, each readable as text on every surface above. */
  ok: string
  warn: string
  danger: string
  info: string
  okSoft: string
  warnSoft: string
  dangerSoft: string
  infoSoft: string
}

/**
 * Light scheme. Solved against bg #F8F9F3 and card #FDFDFB.
 * Text roles: ink 13.1, ink2 8.3, muted 5.3, accent 4.8, accentDeep 7.0.
 * Status as text: ok 5.0, warn 5.6, danger 6.2, info 6.3.
 */
export const LIGHT: SchemeTokens = {
  bg: '#F8F9F3',
  card: '#FDFDFB',
  raised: '#F2F3EA',
  hover: '#F1F2E8',

  ink: '#2C2E1C',
  ink2: '#4A4D35',
  muted: '#666A50',

  border: 'rgba(44, 46, 28, 0.10)',
  borderMid: 'rgba(44, 46, 28, 0.18)',
  borderStrong: 'rgba(44, 46, 28, 0.34)',

  accent: '#697420',
  accentDeep: '#515A1E',
  accentSoft: 'rgba(105, 116, 32, 0.10)',
  accentInk: '#FFFFFF',

  forest: '#3D4127',
  forestMid: '#515A1E',
  forestSoft: 'rgba(61, 65, 39, 0.06)',
  forestInk: '#FFFFFF',

  shadow: 'rgba(61, 65, 39, 0.16)',

  ok: '#1E7A5A',
  warn: '#8A5A00',
  danger: '#B4231A',
  info: '#2F5F8F',
  okSoft: 'rgba(30, 122, 90, 0.10)',
  warnSoft: 'rgba(138, 90, 0, 0.10)',
  dangerSoft: 'rgba(180, 35, 26, 0.08)',
  infoSoft: 'rgba(47, 95, 143, 0.10)',
}

/**
 * Dark scheme. Solved against bg #0D0E09 and card #1E1F16.
 * Text roles: ink 19.4, ink2 16.8, muted 6.1, accent 8.2, accentDeep 12.9.
 * Status as text: ok 10.8, warn 11.1, danger 8.6, info 9.8.
 * Forest flips to the light olive here: a dark olive heading on a near-black
 * page would vanish, and a light olive fill with dark ink is 12.9:1.
 */
export const DARK: SchemeTokens = {
  bg: '#0D0E09',
  card: '#1E1F16',
  raised: '#090906',
  hover: '#282A1F',

  ink: '#FFFFFF',
  ink2: '#EEEFEB',
  muted: '#8E9370',

  border: 'rgba(206, 217, 140, 0.10)',
  borderMid: '#40432D',
  borderStrong: '#5C6144',

  accent: '#A0B13E',
  accentDeep: '#CED98C',
  accentSoft: 'rgba(160, 177, 62, 0.12)',
  accentInk: '#0D0E09',

  forest: '#CED98C',
  forestMid: '#A0B13E',
  forestSoft: 'rgba(206, 217, 140, 0.08)',
  forestInk: '#0D0E09',

  shadow: 'rgba(0, 0, 0, 0.35)',

  ok: '#7DD3A6',
  warn: '#E9BE5A',
  danger: '#F29488',
  info: '#93BCE6',
  okSoft: 'rgba(125, 211, 166, 0.12)',
  warnSoft: 'rgba(233, 190, 90, 0.12)',
  dangerSoft: 'rgba(242, 148, 136, 0.10)',
  infoSoft: 'rgba(147, 188, 230, 0.12)',
}

/**
 * Mantine colour ramps, kept for components that take a colour name.
 *
 * `olive` is split by scheme: steps 0-5 are solved against the dark card, steps
 * 6-9 against the light page, and primaryShade picks 3 on dark and 6 on light.
 * A single shade cannot serve both: the lightness that reads on near-black is
 * the one that vanishes on near-white.
 */
export const OLIVE_RAMP = [
  '#FAFCF3', // 0  16.06:1 on dark
  '#EFF3D8', // 1  14.64:1 on dark
  '#CED98C', // 2  11.03:1 on dark: key figures, active nav
  '#A0B13E', // 3   7.01:1 on dark: PRIMARY on dark surfaces
  '#7F8C34', // 4   4.52:1 on dark: the floor for body text
  '#646E2B', // 5   3.01:1 on dark: boundaries and large text only
  '#697420', // 6   4.81:1 on light: PRIMARY on light surfaces
  '#515A1E', // 7   7.01:1 on light: emphasis on light
  '#3D4127', // 8  10.00:1 on light: structural dark olive
  '#212315', // 9  15.07:1 on light: deepest ink
] as const

/** Neutrals warmed into the brand hue. Ratios against dark[7], the dark body. */
export const DARK_RAMP = [
  '#FFFFFF', // 0 primary text      19.37:1
  '#EEEFEB', // 1 secondary text    16.77:1
  '#B0B39A', // 2 icons, subtitles   9.01:1
  '#878C66', // 3 dimmed text        5.51:1
  '#40432D', // 4 borders, dividers
  '#2A2C21', // 5 hover
  '#1E1F16', // 6 card, panel
  '#0D0E09', // 7 body
  '#090906', // 8 header, navbar
  '#040503', // 9 deepest base
] as const

/**
 * Motion. Three durations and two curves, so every transition in the product
 * moves at one of three speeds. `prefers-reduced-motion` collapses them to
 * zero in index.css.
 */
export const MOTION = {
  fast: '120ms',
  base: '200ms',
  slow: '420ms',
  easeOut: 'cubic-bezier(0.22, 1, 0.36, 1)',
  easeInOut: 'cubic-bezier(0.65, 0, 0.35, 1)',
} as const

/** Text-on-surface pairings the contrast script holds to WCAG AA. */
export const CONTRAST_PAIRS: { text: keyof SchemeTokens; surface: keyof SchemeTokens }[] = [
  ...(['ink', 'ink2', 'muted', 'accent', 'accentDeep', 'ok', 'warn', 'danger', 'info'] as const).flatMap(
    (text) => (['bg', 'card', 'raised', 'hover'] as const).map((surface) => ({ text, surface })),
  ),
  { text: 'accentInk', surface: 'accent' },
  { text: 'forestInk', surface: 'forest' },
  { text: 'forestInk', surface: 'forestMid' },
]
