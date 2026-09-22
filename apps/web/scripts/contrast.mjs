// Holds every text-on-surface pairing in src/tokens.ts to WCAG AA (4.5:1),
// in both colour schemes. Runs as part of `npm run lint`, so a token that
// drifts below the floor fails the build instead of shipping unreadable text.
//
//   node scripts/contrast.mjs
//
// Node strips the types from tokens.ts itself (Node 23+); the file has no
// imports, which is what makes that possible.

import { CONTRAST_PAIRS, DARK, LIGHT } from '../src/tokens.ts'

const FLOOR = 4.5

function channel(c) {
  const v = c / 255
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
}

function luminance(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) throw new Error(`contrast: ${hex} is not a six-digit hex colour; only solid colours can be checked`)
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16))
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

let failures = 0
for (const [name, scheme] of [
  ['light', LIGHT],
  ['dark', DARK],
]) {
  for (const { text, surface } of CONTRAST_PAIRS) {
    const r = ratio(scheme[text], scheme[surface])
    if (r < FLOOR) {
      failures += 1
      console.error(`  ${name}: ${text} on ${surface} is ${r.toFixed(2)}:1, below ${FLOOR}:1`)
    }
  }
}

if (failures) {
  console.error(`contrast: ${failures} pairing(s) below WCAG AA`)
  process.exit(1)
}
console.log(`contrast: all ${CONTRAST_PAIRS.length * 2} pairings clear ${FLOOR}:1`)
