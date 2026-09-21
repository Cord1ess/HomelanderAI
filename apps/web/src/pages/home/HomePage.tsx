import {
  Anchor,
  Box,
  Button,
  Container,
  Group,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
} from '@mantine/core'
import {
  IconArrowRight,
  IconCheck,
  IconEye,
  IconFileCheck,
  IconHistory,
  IconShieldLock,
  IconStethoscope,
} from '@tabler/icons-react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'

import { BrandIcon } from '../../components/BrandIcon'
import { useAuth } from '../../context/AuthContext'

/**
 * Public landing page — follows smooth-cosmos-suite.lovable.app.
 *
 * Design system:
 *  - Space Grotesk Variable for all display headlines (.neo-display)
 *  - Space Grotesk Variable for nav, body, buttons
 *  - Forest green (#1C3829) as primary brand colour
 *  - Clinical teal (#2f7f7b) as accent
 *  - Warm off-white (#f7f5f0) background
 *  - No hard black borders — soft 10% opacity borders throughout
 */

const FEATURES = [
  {
    icon: IconStethoscope,
    title: 'TB chest X-ray screening',
    body: 'The vision arm screens chest radiographs for tuberculosis. Declared medical history is weighed against findings to reach a score.',
  },
  {
    icon: IconEye,
    title: 'Explainable Grad-CAM',
    body: 'Every recommendation ships with the heatmap and the reasoning — the underwriter sees evidence, not just a score.',
  },
  {
    icon: IconFileCheck,
    title: 'Write-once decisions',
    body: 'Four defined actions, no reject button. Escalation to a senior underwriter is how a declined case stays humane.',
  },
  {
    icon: IconHistory,
    title: 'Full audit trail',
    body: 'Model runs, human decisions and identities are timestamped end to end — a record you can defend.',
  },
]

const STEPS = [
  {
    n: '01',
    title: 'Evidence intake',
    body: 'Applications, imaging, and clinical history become one structured case file before scoring begins.',
  },
  {
    n: '02',
    title: 'Composite scoring',
    body: 'Six weighted factors produce one advisory index with every contribution open to inspection.',
  },
  {
    n: '03',
    title: 'Human decision',
    body: 'A licensed underwriter records the final action and rationale in an immutable audit trail.',
  },
]

const STATS = [
  { value: '94%', label: 'Evidence coverage' },
  { value: '6', label: 'Composite factors' },
  { value: '100%', label: 'Audit logged' },
]

const navLinkStyle: CSSProperties = {
  fontWeight: 500,
  fontSize: '0.875rem',
  color: 'var(--neo-ink)',
  textDecoration: 'none',
  opacity: 0.55,
  transition: 'opacity 0.15s ease',
  fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif',
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
            {/* Brand */}
            <Group gap="xs" align="center">
              <Box className="neo-brand-chip neo-press" p={4}>
                <BrandIcon width={36} height={36} style={{ display: 'block' }} />
              </Box>
              <Text
                style={{
                  fontSize: '1rem',
                  fontWeight: 600,
                  letterSpacing: '-0.01em',
                  fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif',
                  color: 'var(--neo-ink)',
                }}
              >
                homelander
              </Text>
            </Group>

            {/* Nav links */}
            <Group gap="xl" visibleFrom="md">
              <Anchor style={navLinkStyle} href="#platform">Platform</Anchor>
              <Anchor style={navLinkStyle} href="#evidence">Evidence</Anchor>
              <Anchor style={navLinkStyle} href="#compliance">Compliance</Anchor>
            </Group>

            {/* CTAs */}
            <Group gap="md">
              <Anchor
                component={Link}
                to="/auth"
                style={{ ...navLinkStyle, opacity: 0.4 }}
                visibleFrom="sm"
              >
                Sign in
              </Anchor>
              <Box className="neo-press">
                <Button
                  component={Link}
                  to={ctaTo}
                  size="sm"
                  radius={4}
                  style={{
                    background: 'var(--neo-forest)',
                    border: 'none',
                    fontWeight: 600,
                    fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif',
                    boxShadow: '0 1px 4px rgba(28,56,41,0.2)',
                  }}
                >
                  Open console
                </Button>
              </Box>
            </Group>
          </Group>
        </Container>
      </Box>

      {/* ── Hero ────────────────────────────────────────────────────── */}
      <Box py={{ base: 72, md: 104 }}>
        <Container size="lg">
          <SimpleGrid cols={{ base: 1, lg: 2 }} spacing={64}>

            {/* Left — text */}
            <Stack gap="xl">
              {/* Decision support badge */}
              <div>
                <span className="neo-decision-badge">
                  Decision support · Not a medical device
                </span>
              </div>

              <Text
                className="home-rise home-rise-1 neo-display"
                style={{ fontSize: 'clamp(2.4rem, 5.5vw, 3.8rem)', fontWeight: 700 }}
              >
                Underwriting judgment,{' '}
                <span className="neo-underline">backed by explainable</span> evidence.
              </Text>

              <Text
                className="home-rise home-rise-2"
                style={{
                  fontSize: '0.95rem',
                  lineHeight: 1.75,
                  maxWidth: 480,
                  color: 'var(--neo-ink)',
                  opacity: 0.6,
                  fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif',
                }}
              >
                HomelanderAI connects chest imaging, declared history, and structured
                risk factors so licensed underwriters can make defensible decisions
                with the complete record in view.
              </Text>

              {/* CTA buttons */}
              <Group gap="sm" className="home-rise home-rise-3">
                <Box className="neo-press">
                  <Button
                    component={Link}
                    to={ctaTo}
                    size="md"
                    radius={4}
                    style={{
                      background: 'var(--neo-forest)',
                      border: 'none',
                      fontWeight: 600,
                      fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif',
                      boxShadow: '0 2px 12px rgba(28,56,41,0.2)',
                    }}
                  >
                    Open a case file
                  </Button>
                </Box>
                <Box className="neo-press">
                  <Button
                    component="a"
                    href="#platform"
                    variant="default"
                    size="md"
                    radius={4}
                    rightSection={<IconArrowRight size={15} />}
                    style={{
                      border: '1px solid var(--neo-border-mid)',
                      fontWeight: 600,
                      background: 'var(--neo-card)',
                      color: 'var(--neo-ink)',
                      fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif',
                      boxShadow: '0 1px 4px var(--neo-shadow)',
                    }}
                  >
                    View methodology
                  </Button>
                </Box>
              </Group>

              {/* Stats */}
              <Group gap="sm" className="home-rise home-rise-4" wrap="wrap">
                {STATS.map((s) => (
                  <div key={s.label} className="neo-stat-pill">
                    <span className="neo-stat-value">{s.value}</span>
                    <span className="neo-stat-label">{s.label}</span>
                  </div>
                ))}
              </Group>
            </Stack>

            {/* Right — mock case card */}
            <Group justify="center" align="center" className="home-rise home-rise-3">
              <Box className="neo-case-card">
                <Box className="neo-case-card__header">
                  <Text size="xs" fw={600} tt="uppercase" style={{ letterSpacing: '0.1em', opacity: 0.45, fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
                    Composite risk
                  </Text>
                  <Group gap="xs" align="center" mt={4}>
                    <div className="neo-case-card__dot" />
                    <Text size="xs" fw={500} style={{ opacity: 0.4, fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
                      Case #HOM-20938
                    </Text>
                  </Group>
                </Box>

                <Box className="neo-case-card__score-wrap">
                  <svg width="110" height="65" viewBox="0 0 110 65">
                    <path d="M 8 60 A 47 47 0 0 1 102 60" fill="none" stroke="var(--neo-border)" strokeWidth="3" />
                    <path d="M 8 60 A 47 47 0 0 1 76 17" fill="none" stroke="var(--neo-accent)" strokeWidth="3.5" strokeLinecap="round" />
                  </svg>
                  <Text className="neo-display" style={{ fontSize: '2.2rem', marginTop: '-6px', color: 'var(--neo-ink)' }}>
                    62
                  </Text>
                  <Text size="xs" style={{ opacity: 0.4, marginTop: 2, fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
                    Moderate · Tier 2
                  </Text>
                </Box>

                <Stack gap={0} className="neo-case-card__rows">
                  {[
                    { label: 'Imaging', value: 'Screened', ok: true },
                    { label: 'Factors', value: '4 of 6 clear', ok: true },
                    { label: 'Decision', value: 'Pending review', ok: false },
                  ].map((row) => (
                    <Group key={row.label} justify="space-between" className="neo-case-card__row">
                      <Text size="xs" style={{ opacity: 0.45, fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
                        {row.label}
                      </Text>
                      <Group gap={5} align="center">
                        {row.ok && <IconCheck size={11} color="var(--neo-accent)" strokeWidth={3} />}
                        <Text size="xs" fw={600} style={{ fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
                          {row.value}
                        </Text>
                      </Group>
                    </Group>
                  ))}
                </Stack>
              </Box>
            </Group>
          </SimpleGrid>
        </Container>
      </Box>

      {/* ── How it reads a case ─────────────────────────────────────── */}
      <Box id="platform" py={{ base: 64, md: 88 }} className="neo-steps-band">
        <Container size="lg">
          <Stack gap={48}>
            <Stack gap={6} align="center" ta="center">
              <Text className="neo-eyebrow">01 — How it reads a case</Text>
              <Text
                className="neo-display"
                style={{ fontSize: 'clamp(1.6rem, 3.5vw, 2.4rem)', color: 'var(--neo-ink)' }}
              >
                One precise system from first intake to final audit.
              </Text>
            </Stack>

            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
              {STEPS.map((step) => (
                <Box key={step.n} className="neo-step">
                  <Text className="neo-step__number">{step.n}</Text>
                  <Text fw={600} size="md" mt="md" mb={6} style={{ color: 'var(--neo-ink)', fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
                    {step.title}
                  </Text>
                  <Text size="sm" style={{ opacity: 0.55, lineHeight: 1.65, fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
                    {step.body}
                  </Text>
                </Box>
              ))}
            </SimpleGrid>
          </Stack>
        </Container>
      </Box>

      {/* ── Feature cards ───────────────────────────────────────────── */}
      <Box id="evidence" py={{ base: 64, md: 88 }}>
        <Container size="lg">
          <Stack gap={44}>
            <Stack gap={6} align="center" ta="center">
              <Text className="neo-eyebrow">Built for the two moments that matter</Text>
              <Text
                className="neo-display"
                style={{ fontSize: 'clamp(1.6rem, 3.5vw, 2.4rem)', color: 'var(--neo-ink)' }}
              >
                What the console gives you
              </Text>
            </Stack>

            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="lg">
              {FEATURES.map((f) => (
                <Box
                  key={f.title}
                  className="neo-card neo-lift"
                  p="lg"
                  style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}
                >
                  <ThemeIcon
                    size={38}
                    radius={4}
                    variant="light"
                    color="clinical"
                    style={{ border: '1px solid var(--neo-border)' }}
                  >
                    <f.icon size={18} />
                  </ThemeIcon>
                  <Text fw={600} size="sm" style={{ color: 'var(--neo-ink)', fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
                    {f.title}
                  </Text>
                  <Text size="sm" style={{ opacity: 0.55, lineHeight: 1.65, fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
                    {f.body}
                  </Text>
                </Box>
              ))}
            </SimpleGrid>

            {/* Security note */}
            <Group id="compliance" gap="xs" justify="center" mt="xs">
              <IconShieldLock size={15} color="var(--neo-accent)" />
              <Text size="sm" fw={500} style={{ color: 'var(--neo-ink)', opacity: 0.5, fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
                Decisions require licensed human sign-off. Health data is minimised and never stored in the browser.
              </Text>
            </Group>
          </Stack>
        </Container>
      </Box>

      {/* ── CTA Band ────────────────────────────────────────────────── */}
      <Box className="neo-cta-band" py={{ base: 80, md: 112 }}>
        <Container size="md">
          <Stack gap="xl" align="center" ta="center">
            <Text
              className="neo-display"
              style={{ fontSize: 'clamp(1.9rem, 4.5vw, 3.2rem)' }}
            >
              Move from evidence to decision{' '}
              <span className="neo-underline">without a visual reset.</span>
            </Text>
            <Text style={{ opacity: 0.5, maxWidth: 460, fontSize: '0.9rem', lineHeight: 1.7, fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif', color: '#fff' }}>
              One precise system from first intake to final audit.
            </Text>
            <Box className="neo-press">
              <Button
                component={Link}
                to={ctaTo}
                size="lg"
                radius={4}
                rightSection={<IconArrowRight size={17} />}
                style={{
                  background: 'rgba(255,255,255,0.1)',
                  border: '1px solid rgba(255,255,255,0.22)',
                  fontWeight: 600,
                  fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif',
                  backdropFilter: 'blur(8px)',
                  paddingInline: '2rem',
                  color: '#fff',
                  boxShadow: '0 4px 24px rgba(0,0,0,0.2)',
                }}
              >
                Enter the workspace
              </Button>
            </Box>
          </Stack>
        </Container>
      </Box>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      <Box style={{ borderTop: '1px solid var(--neo-border)' }} py="lg">
        <Container size="lg">
          <Group justify="space-between" wrap="wrap">
            <Text size="sm" fw={600} style={{ color: 'var(--neo-ink)', opacity: 0.45, fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
              HomelanderAI · Underwriting decision support
            </Text>
            <Text size="sm" fw={500} style={{ color: 'var(--neo-ink)', opacity: 0.35, fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
              © {new Date().getFullYear()} HomelanderAI
            </Text>
          </Group>
          <Text size="xs" mt="md" style={{ opacity: 0.35, maxWidth: 680, lineHeight: 1.65, color: 'var(--neo-ink)', fontFamily: '"Space Grotesk Variable", "Space Grotesk", sans-serif' }}>
            Research software. Not a medical device, not clinically validated, and not approved by any
            regulatory body. Every output is a recommendation for a licensed underwriter to review —
            the platform does not diagnose and never issues an automated denial.
          </Text>
        </Container>
      </Box>

    </Box>
  )
}

