// Start the Mirai container before the dev servers. Runs as `predev`.
//
// Mirai is the mammogram reader. It runs in Docker because it pins Python 3.8,
// which cannot share the API's environment. Starting it here means `npm run
// dev` is still the whole setup.
//
// If Docker is not running this says so plainly and lets the app start
// anyway: every other reader works without it, and an application with a
// mammogram will say on screen that the reader is not running. Refusing to
// start the whole app over one reader would be the worse failure.

import { spawnSync } from 'node:child_process'

const run = (args) => spawnSync('docker', args, { encoding: 'utf8' })

const warn = (lines) => {
  const bar = '─'.repeat(72)
  console.warn(`\n${bar}\n${lines.join('\n')}\n${bar}\n`)
}

const info = run(['info', '--format', '{{.ServerVersion}}'])
if (info.status !== 0) {
  warn([
    '  Mammogram reader NOT started: Docker is not running.',
    '',
    '  Start Docker Desktop, then run:  docker compose up -d mirai',
    '  The rest of the app works meanwhile; mammograms will say the reader',
    '  is not running until it is.',
  ])
  process.exit(0)
}

const up = run(['compose', 'up', '-d', 'mirai'])
if (up.status !== 0) {
  warn([
    '  Mammogram reader could not be started:',
    '',
    ...(up.stderr || up.stdout || '').trim().split('\n').map((l) => `  ${l}`),
  ])
  process.exit(0)
}

console.log('Mammogram reader (Mirai) is running on http://127.0.0.1:5000 — about 45 s per exam.')
