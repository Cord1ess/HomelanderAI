import { Anchor, Box, Button, Container, Group, SimpleGrid, Stack, Table, Text } from '@mantine/core'
import { IconArrowRight } from '@tabler/icons-react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'

import { BrandIcon } from '../../components/BrandIcon'
import { ThemeToggle } from '../../components/ThemeToggle'
import { useAuth } from '../../context/AuthContext'
import { PlatformAnimation } from './PlatformAnimation'

/**
 * Public landing page. Sells to insurers, so it answers a buyer's questions in
 * order: what this does, how it works, what you get, what it will not do.
 *
 * It names no model, dataset or metric. Readers are added and retrained
 * without the process changing, and a page that lists them goes stale the
 * week after it is written. What is stated here is the shape of the platform,
 * and every sentence of that is true of the code.
 */

// The three stages, in the order the platform runs them.
const STAGES = [
  {
    n: '1',
    title: 'You take the data',
    lead: 'Everything the client hands you, in one place.',
    body: 'Your team enters the client, the cover they are asking for and their health questions, then drops every document they brought into one place. The platform works out what each file is, an operator confirms it, and identifiers inside the files are stripped before anything is stored.',
  },
  {
    n: '2',
    title: 'AI reads it',
    lead: 'Each document goes to the reader built for it.',
    body: 'Scans, traces, lab values and notes each have their own reader. Every reader returns a score and the reasons behind it, and the readings become one risk score for the application. Declared history adjusts that score by rules your underwriters can read.',
  },
  {
    n: '3',
    title: 'Insurance is decided',
    lead: 'A plan is suggested. A person decides.',
    body: 'The score places the application in a tier, and the tier suggests a plan and a premium for the cover requested, under boundaries and rates your company sets. An underwriter or a medical professional records the decision, and the client follows it from their own portal.',
  },
]

// What the platform reads today, by kind rather than by model.
const READS = [
  {
    title: 'Imaging',
    body: 'Chest and retinal images read for the conditions an insurer prices on, with a heatmap over the region each reader looked at.',
  },
  {
    title: 'Signals',
    body: 'Twelve-lead ECG traces read for rhythm and conduction abnormalities, and for how old the heart looks.',
  },
  {
    title: 'Lab results and lifestyle',
    body: 'Routine blood values and a few lifestyle answers, read for mortality relative to age.',
  },
  {
    title: 'Documents',
    body: 'Notes and reports stored with the application for the underwriter to read. Readers for these are added without changing how your team works.',
  },
]

// The tiers, in words. The boundaries and rates are the company's own.
const TIERS = [
  { tier: 'Low', action: 'Cleared at the standard rate', who: 'One-click confirmation by an underwriter' },
  { tier: 'Moderate', action: 'Approved with an adjusted premium', who: 'The underwriter sets the final rate' },
  { tier: 'Elevated', action: 'Read by a medical professional', who: 'Never decided by the platform' },
  { tier: 'Not scorable', action: 'More evidence requested', who: 'The client is told what is missing' },
]

const WHAT_YOU_GET = [
  {
    title: 'The reasons, not just a number',
    body: 'Every score shows what moved it and by how much. An underwriter can see whether to trust it before they act on it.',
  },
  {
    title: 'A record that holds up',
    body: 'Every reading, every decision and the person who made it are written to an append-only log chained by hash. Altering one entry breaks every entry after it.',
  },
  {
    title: 'Your data stays yours',
    body: 'Each company sees only its own applications. Files are served through the API with every request checked against your account, never from a public address.',
  },
  {
    title: 'Clients kept informed',
    body: 'Every client gets a portal sign-in: where their application is, when to expect an answer, what is still needed, and the offer once it is decided.',
  },
]

const navLinkStyle: CSSProperties = {
  fontWeight: 500,
  fontSize: '0.875rem',
  color: 'var(--neo-ink)',
  textDecoration: 'none',
  opacity: 0.55,
  transition: 'opacity var(--motion-fast) var(--ease-out)',
  fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif',
}

const GROTESK = '"Space Grotesk Variable", "Space Grotesk", sans-serif'

const filledButtonStyle: CSSProperties = {
  background: 'var(--neo-forest)',
  border: 'none',
  fontWeight: 600,
  fontFamily: GROTESK,
  color: 'var(--neo-forest-ink)',
}

/** The secondary button: same shape as the filled one, quieter. */
const outlineButtonStyle: CSSProperties = {
  border: '1px solid var(--neo-border-mid)',
  fontWeight: 600,
  background: 'var(--neo-card)',
  color: 'var(--neo-ink)',
  fontFamily: GROTESK,
}

export function HomePage() {
  const { isAuthenticated } = useAuth()
  const ctaTo = isAuthenticated ? '/queue' : '/auth'

  return (
    <Box className="neo-shell">
      {/* ── Nav ─────────────────────────────────────────────────────── */}
      <Box style={{ borderBottom: '1px solid var(--neo-border)' }}>
        <Container size="lg" py="md">
          <Group justify="space-between" align="center">
            <Group gap="xs" align="center">
              <Box className="neo-brand-chip neo-press" p={4}>
                <BrandIcon width={36} height={36} style={{ display: 'block' }} />
              </Box>
              <Text
                style={{
                  fontSize: '1rem',
                  fontWeight: 600,
                  letterSpacing: '-0.01em',
                  fontFamily: GROTESK,
                  color: 'var(--neo-ink)',
                }}
              >
                Homelander AI
              </Text>
            </Group>

            <Group gap="xl" visibleFrom="md">
              <Anchor style={navLinkStyle} href="#how">How it works</Anchor>
              <Anchor style={navLinkStyle} href="#reads">What it reads</Anchor>
              <Anchor style={navLinkStyle} href="#tiers">Tiers</Anchor>
              <Anchor style={navLinkStyle} href="#limits">Limits</Anchor>
            </Group>

            {/* Two audiences, two buttons. Staff sign in to the console; a
                client checks their own application. */}
            <Group gap="sm">
              <ThemeToggle />
              <Box className="neo-press">
                <Button component={Link} to="/auth?as=client" variant="default" size="sm" radius={4} style={outlineButtonStyle}>
                  Check status
                </Button>
              </Box>
              <Box className="neo-press">
                <Button component={Link} to={ctaTo} size="sm" radius={4} style={filledButtonStyle}>
                  {isAuthenticated ? 'Open console' : 'Sign in'}
                </Button>
              </Box>
            </Group>
          </Group>
        </Container>
      </Box>

      {/* ── Hero ────────────────────────────────────────────────────── */}
      <Box py={{ base: 56, md: 88 }}>
        <Container size="lg">
          <SimpleGrid cols={{ base: 1, lg: 2 }} spacing={48} style={{ alignItems: 'center' }}>
            <Stack gap="lg">
              <Text className="neo-eyebrow home-rise home-rise-1" style={{ color: 'var(--neo-accent-deep)' }}>
                Underwriting decision support for insurers
              </Text>
              <Text
                component="h1"
                className="home-rise home-rise-1 neo-display"
                style={{ fontSize: 'clamp(2rem, 4.2vw, 3.1rem)', margin: 0, color: 'var(--neo-forest)' }}
              >
                Every file a client hands you, read by AI.
                <br />
                Every decision, made by your people.
              </Text>
              <Text
                className="home-rise home-rise-2"
                style={{ fontSize: '1.05rem', lineHeight: 1.65, maxWidth: 520, color: 'var(--neo-ink-2)', fontFamily: GROTESK }}
              >
                A client can pass a questionnaire and a nurse check while carrying early disease
                nobody has looked for. Homelander AI reads the medical evidence your underwriters
                already collect, scores it, and puts the reasons in front of the person deciding.
              </Text>

              <Group gap="sm" className="home-rise home-rise-3">
                <Box className="neo-press">
                  <Button component={Link} to={ctaTo} size="md" radius={4} style={filledButtonStyle}>
                    {isAuthenticated ? 'Open console' : 'Sign in'}
                  </Button>
                </Box>
                <Box className="neo-press">
                  <Button component={Link} to="/auth?as=client" variant="default" size="md" radius={4} style={outlineButtonStyle}>
                    Check status
                  </Button>
                </Box>
              </Group>

              <Text size="sm" className="home-rise home-rise-3" style={{ color: 'var(--neo-muted)', fontFamily: GROTESK, maxWidth: 460 }}>
                Staff sign in to the console. Clients check their application with the portal ID they were given.
              </Text>

              <Anchor
                href="#how"
                className="home-rise home-rise-3"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  width: 'fit-content',
                  color: 'var(--neo-forest)',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  fontFamily: GROTESK,
                }}
              >
                See how it works <IconArrowRight size={15} />
              </Anchor>
            </Stack>

            <Group justify="center" className="home-rise home-rise-3">
              <PlatformAnimation />
            </Group>
          </SimpleGrid>
        </Container>
      </Box>

      {/* ── How it works: the timeline ──────────────────────────────── */}
      <Box id="how" py={{ base: 56, md: 80 }} className="neo-steps-band">
        <Container size="lg">
          <Stack gap="xl">
            <Stack gap={6}>
              <Text className="neo-eyebrow" style={{ color: 'var(--neo-accent-deep)' }}>How it works</Text>
              <Text className="neo-display" style={{ fontSize: 'clamp(1.6rem, 3vw, 2.2rem)', color: 'var(--neo-forest)' }}>
                Three stages, in this order, every time.
              </Text>
            </Stack>

            <ol className="timeline">
              {STAGES.map((stage) => (
                <li key={stage.n} className="timeline__stage">
                  <div className="timeline__marker">
                    <span className="timeline__number">{stage.n}</span>
                  </div>
                  <div className="timeline__body neo-card">
                    <Text fw={700} style={{ fontSize: '1.15rem', fontFamily: GROTESK, color: 'var(--neo-ink)' }}>
                      {stage.title}
                    </Text>
                    <Text fw={600} size="sm" mt={2} style={{ color: 'var(--neo-accent-deep)', fontFamily: GROTESK }}>
                      {stage.lead}
                    </Text>
                    <Text size="sm" mt="xs" style={{ lineHeight: 1.65, color: 'var(--neo-ink-2)', fontFamily: GROTESK }}>
                      {stage.body}
                    </Text>
                  </div>
                </li>
              ))}
            </ol>
          </Stack>
        </Container>
      </Box>

      {/* ── What it reads ───────────────────────────────────────────── */}
      <Box id="reads" py={{ base: 56, md: 80 }}>
        <Container size="lg">
          <Stack gap="xl">
            <Stack gap={6} maw={640}>
              <Text className="neo-eyebrow" style={{ color: 'var(--neo-accent-deep)' }}>What it reads</Text>
              <Text className="neo-display" style={{ fontSize: 'clamp(1.6rem, 3vw, 2.2rem)', color: 'var(--neo-forest)' }}>
                Drop the file. The platform finds the reader.
              </Text>
              <Text size="sm" style={{ lineHeight: 1.65, color: 'var(--neo-ink-2)', fontFamily: GROTESK }}>
                Your team never picks a model. Each kind of evidence has a reader, readers are added
                and retrained without the process changing, and each one says on screen what its
                number is worth.
              </Text>
            </Stack>
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
              {READS.map((r) => (
                <Box key={r.title} className="neo-card neo-lift" p="lg">
                  <Text fw={700} style={{ fontFamily: GROTESK, color: 'var(--neo-ink)' }}>{r.title}</Text>
                  <Text size="sm" mt="xs" style={{ lineHeight: 1.6, color: 'var(--neo-ink-2)', fontFamily: GROTESK }}>
                    {r.body}
                  </Text>
                </Box>
              ))}
            </SimpleGrid>
          </Stack>
        </Container>
      </Box>

      {/* ── Tiers ───────────────────────────────────────────────────── */}
      <Box id="tiers" py={{ base: 56, md: 80 }} className="neo-steps-band">
        <Container size="lg">
          <SimpleGrid cols={{ base: 1, lg: 2 }} spacing={48} style={{ alignItems: 'start' }}>
            <Stack gap="md">
              <Text className="neo-eyebrow" style={{ color: 'var(--neo-accent-deep)' }}>Tiers</Text>
              <Text className="neo-display" style={{ fontSize: 'clamp(1.6rem, 3vw, 2.2rem)', color: 'var(--neo-forest)' }}>
                A score becomes a tier. A tier suggests a plan.
              </Text>
              <Text size="sm" style={{ lineHeight: 1.65, color: 'var(--neo-ink-2)', fontFamily: GROTESK }}>
                Where the boundaries sit, and what each plan costs at a given cover, are set by your
                company's administrator and recorded every time they change. The premium shown is a
                starting point that scales with the cover requested; the underwriter sets the final
                rate on every approval.
              </Text>
            </Stack>
            <Box className="neo-card" p={0} style={{ overflow: 'hidden' }}>
              <Table verticalSpacing="sm" horizontalSpacing="md" style={{ fontFamily: GROTESK }}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Tier</Table.Th>
                    <Table.Th>What is suggested</Table.Th>
                    <Table.Th>Who decides</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {TIERS.map((t) => (
                    <Table.Tr key={t.tier}>
                      <Table.Td fw={700}>{t.tier}</Table.Td>
                      <Table.Td>{t.action}</Table.Td>
                      <Table.Td style={{ color: 'var(--neo-ink-2)' }}>{t.who}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Box>
          </SimpleGrid>
        </Container>
      </Box>

      {/* ── What you get ────────────────────────────────────────────── */}
      <Box py={{ base: 56, md: 80 }}>
        <Container size="lg">
          <Stack gap="xl">
            <Stack gap={6}>
              <Text className="neo-eyebrow" style={{ color: 'var(--neo-accent-deep)' }}>What you get</Text>
              <Text className="neo-display" style={{ fontSize: 'clamp(1.6rem, 3vw, 2.2rem)', color: 'var(--neo-forest)' }}>
                Built for the day someone asks why.
              </Text>
            </Stack>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
              {WHAT_YOU_GET.map((w) => (
                <Box key={w.title} className="neo-card neo-lift" p="lg">
                  <Text fw={700} style={{ fontFamily: GROTESK, color: 'var(--neo-ink)' }}>{w.title}</Text>
                  <Text size="sm" mt="xs" style={{ lineHeight: 1.65, color: 'var(--neo-ink-2)', fontFamily: GROTESK }}>
                    {w.body}
                  </Text>
                </Box>
              ))}
            </SimpleGrid>
          </Stack>
        </Container>
      </Box>

      {/* ── Limits ──────────────────────────────────────────────────── */}
      <Box id="limits" py={{ base: 48, md: 64 }} className="neo-steps-band">
        <Container size="lg">
          <Stack gap="sm" maw={720}>
            <Text className="neo-eyebrow" style={{ color: 'var(--neo-accent-deep)' }}>Limits</Text>
            <Text className="neo-display" style={{ fontSize: 'clamp(1.4rem, 2.6vw, 1.9rem)', color: 'var(--neo-forest)' }}>
              Decision support. Not a diagnosis, and not a decision.
            </Text>
            <Text size="sm" style={{ lineHeight: 1.65, color: 'var(--neo-ink-2)', fontFamily: GROTESK }}>
              The platform never approves, declines or prices a policy on its own, and no score is
              ever shown to a client. Readers are validated on public data and the screen tells your
              underwriter what each number is worth. This is research software, not a medical device.
            </Text>
          </Stack>
        </Container>
      </Box>

      {/* ── CTA ─────────────────────────────────────────────────────── */}
      <Box className="neo-cta-band" py={{ base: 48, md: 64 }}>
        <Container size="lg">
          <Group justify="space-between" align="center" wrap="wrap" gap="lg">
            <Stack gap={4}>
              <Text className="neo-display" style={{ fontSize: 'clamp(1.4rem, 2.6vw, 2rem)' }}>
                See it read a real file.
              </Text>
              <Text style={{ opacity: 0.75, maxWidth: 440, fontSize: '0.9rem', lineHeight: 1.7, fontFamily: GROTESK, color: 'var(--neo-forest-ink)' }}>
                Sign in, take an application, and watch the score arrive with its reasons.
              </Text>
            </Stack>
            <Box className="neo-press">
              <Button
                component={Link}
                to={ctaTo}
                size="lg"
                radius={4}
                rightSection={<IconArrowRight size={17} />}
                style={{
                  background: 'color-mix(in srgb, var(--neo-forest-ink) 12%, transparent)',
                  border: '1px solid color-mix(in srgb, var(--neo-forest-ink) 24%, transparent)',
                  fontWeight: 600,
                  fontFamily: GROTESK,
                  paddingInline: '2rem',
                  color: 'var(--neo-forest-ink)',
                }}
              >
                {isAuthenticated ? 'Open the console' : 'Sign in'}
              </Button>
            </Box>
          </Group>
        </Container>
      </Box>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      <Box py="lg" style={{ borderTop: '1px solid var(--neo-border)' }}>
        <Container size="lg">
          <Group justify="space-between" wrap="wrap">
            <Text size="xs" style={{ color: 'var(--neo-muted)', fontFamily: GROTESK }}>
              Homelander AI. Underwriting decision support.
            </Text>
            <Text size="xs" style={{ color: 'var(--neo-muted)', fontFamily: GROTESK }}>
              {new Date().getFullYear()} Homelander AI
            </Text>
          </Group>
        </Container>
      </Box>
    </Box>
  )
}
