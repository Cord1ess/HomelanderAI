import {
  Anchor,
  Badge,
  Box,
  Button,
  Container,
  Group,
  SimpleGrid,
  Stack,
  Table,
  Text,
} from '@mantine/core'
import { IconArrowRight } from '@tabler/icons-react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'

import { BrandIcon } from '../../components/BrandIcon'
import { useAuth } from '../../context/AuthContext'
import { PipelineAnimation } from './PipelineAnimation'

/**
 * Public landing page. Sells to insurers, so it answers a buyer's questions in
 * order: what this does, how it works, what you get, what it costs you to be
 * wrong.
 *
 * Every number and capability here is checked against the code. If a model is
 * listed as live it is in the arm registry; if it is listed as coming it is
 * not. Marketing copy that outruns the product is the fastest way to lose an
 * insurer's trust, and the claims are cheap to verify.
 */

// Only what the registry actually runs. Keep in step with app/catalogue.py.
const LIVE_MODELS = [
  {
    name: 'Chest X-ray',
    finds: 'Tuberculosis',
    detail:
      'Reads 18 radiological findings and weighs them into one score. Trained on the Shenzhen set, 0.877 AUC under five-fold cross-validation.',
  },
  {
    name: 'Retinal photo',
    finds: 'Diabetic retinopathy',
    detail:
      'Pretrained on 35,126 EyePACS images and validated against APTOS 2019 at 0.942 AUC.',
  },
]

const COMING = ['Mammogram', 'Skin lesion', 'Clinical notes', 'Lifestyle data', 'Brain MRI']

// The actual pipeline, in the order the code runs it.
const STEPS = [
  {
    n: '01',
    title: 'Your team uploads the file',
    body: 'An operator enters the applicant, the cover requested, and the health questions, then attaches the scan. Identifiers inside the image are stripped on the way in and the original is never written to disk.',
  },
  {
    n: '02',
    title: 'The model reads the evidence',
    body: 'Scoring runs in the background, so the operator is not left waiting with a client in front of them. Each finding is recorded with how much it moved the score.',
  },
  {
    n: '03',
    title: 'Declared history adjusts the score',
    body: 'Thirteen rules apply what the image cannot show. Previously treated tuberculosis with no current symptoms lowers the score; the same history with a current cough raises it.',
  },
  {
    n: '04',
    title: 'An underwriter decides',
    body: 'The platform recommends. A licensed underwriter records the decision, and it is written once. There is no reject button and no automated denial.',
  },
]

// The tiers from app/plans.py, with the premiums that go with them.
const TIERS = [
  { band: '0 to 30', name: 'Standard', action: 'Cleared at baseline rates', who: 'One-click confirmation' },
  { band: '30 to 65', name: 'Standard with adjustment', action: 'Approve with a rate adjustment', who: 'Underwriter sets the final rate' },
  { band: 'Above 65', name: 'Senior review', action: 'Full evidence pack routed onward', who: 'Senior underwriter, never automated' },
  { band: 'No score', name: 'Not assessable', action: 'More evidence requested', who: 'Underwriter asks for what is missing' },
]

const WHAT_YOU_GET = [
  {
    title: 'The reasoning, not just a number',
    body: 'Each score shows which findings drove it and by how much, with a heatmap over the region the model read. An underwriter can see whether to trust it.',
  },
  {
    title: 'A record that holds up',
    body: 'Every model run, every decision, and the person who made it are written to an append-only log chained by hash. Altering one entry breaks every entry after it, and the chain is re-checked on every read.',
  },
  {
    title: 'Your data stays yours',
    body: 'Each carrier sees only its own applications. Scans are served through the API with the request checked against your account, never from a public URL.',
  },
  {
    title: 'Honest about its limits',
    body: 'Where a model has only been tested on one hospital, the screen says so next to the score. You are told what the number is worth.',
  },
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

const GROTESK = '"Space Grotesk Variable", "Space Grotesk", sans-serif'

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
                homelander
              </Text>
            </Group>

            <Group gap="xl" visibleFrom="md">
              <Anchor style={navLinkStyle} href="#how">How it works</Anchor>
              <Anchor style={navLinkStyle} href="#screening">Screening</Anchor>
              <Anchor style={navLinkStyle} href="#tiers">Tiers</Anchor>
              <Anchor style={navLinkStyle} href="#limits">Limits</Anchor>
            </Group>

            <Group gap="md">
              <Anchor component={Link} to="/auth?as=client" style={navLinkStyle} visibleFrom="sm">
                Client portal
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
                    fontFamily: GROTESK,
                    color: '#FFFFFF',
                  }}
                >
                  {isAuthenticated ? 'Open console' : 'Sign in'}
                </Button>
              </Box>
            </Group>
          </Group>
        </Container>
      </Box>

      {/* ── Hero ────────────────────────────────────────────────────── */}
      <Box py={{ base: 64, md: 96 }}>
        <Container size="lg">
          <SimpleGrid cols={{ base: 1, lg: 2 }} spacing={56} style={{ alignItems: 'center' }}>
            <Stack gap="lg">
              <div>
                <span className="neo-decision-badge">
                  For insurers. Decision support, not a medical device.
                </span>
              </div>

              <Text
                className="home-rise home-rise-1 neo-display"
                style={{ fontSize: 'clamp(2.2rem, 5vw, 3.5rem)', fontWeight: 700 }}
              >
                Find the risk <span className="neo-underline">before</span> you write the policy.
              </Text>

              <Text
                className="home-rise home-rise-2"
                style={{
                  fontSize: '0.95rem',
                  lineHeight: 1.75,
                  maxWidth: 470,
                  color: 'var(--neo-ink)',
                  opacity: 0.62,
                  fontFamily: GROTESK,
                }}
              >
                An applicant can pass a questionnaire and a nurse check while carrying
                early disease no one has looked for. Six months of premium does not
                cover the claim that follows. We screen the medical evidence your
                underwriters already collect, and show them what it says.
              </Text>

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
                      fontFamily: GROTESK,
                      color: '#FFFFFF',
                    }}
                  >
                    Open the console
                  </Button>
                </Box>
                <Box className="neo-press">
                  <Button
                    component="a"
                    href="#how"
                    variant="default"
                    size="md"
                    radius={4}
                    rightSection={<IconArrowRight size={15} />}
                    style={{
                      border: '1px solid var(--neo-border-mid)',
                      fontWeight: 600,
                      background: 'var(--neo-card)',
                      color: 'var(--neo-ink)',
                      fontFamily: GROTESK,
                    }}
                  >
                    See how it works
                  </Button>
                </Box>
              </Group>

              {/* The other audience. A client who was emailed a portal link and
                  lands here instead needs one obvious way through. */}
              <Text
                size="sm"
                className="home-rise home-rise-3"
                style={{ color: 'var(--neo-accent-deep)', fontFamily: GROTESK }}
              >
                Applied through one of our carriers?{' '}
                <Anchor
                  component={Link}
                  to="/auth?as=client"
                  style={{
                    color: 'var(--neo-forest)',
                    fontWeight: 600,
                    textDecoration: 'underline',
                    textUnderlineOffset: 3,
                  }}
                >
                  Check your application
                </Anchor>
              </Text>
            </Stack>

            <Group justify="center" className="home-rise home-rise-3">
              <PipelineAnimation />
            </Group>
          </SimpleGrid>
        </Container>
      </Box>

      {/* ── How it works ────────────────────────────────────────────── */}
      <Box id="how" py={{ base: 56, md: 80 }} className="neo-steps-band">
        <Container size="lg">
          <Stack gap={44}>
            <Stack gap={8} align="center" ta="center">
              <Text className="neo-eyebrow">How it works</Text>
              <Text className="neo-display" style={{ fontSize: 'clamp(1.6rem, 3.5vw, 2.3rem)', color: 'var(--neo-ink)' }}>
                Four steps, one page, one submit.
              </Text>
              <Text size="sm" style={{ opacity: 0.55, maxWidth: 520, lineHeight: 1.7, fontFamily: GROTESK }}>
                Your operator works through it with the client in the room. Nothing is
                lost if they jump around or the client corrects themselves.
              </Text>
            </Stack>

            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="lg">
              {STEPS.map((step) => (
                <Box key={step.n} className="neo-step">
                  <Text className="neo-step__number">{step.n}</Text>
                  <Text fw={600} size="md" mt="md" mb={6} style={{ color: 'var(--neo-ink)', fontFamily: GROTESK }}>
                    {step.title}
                  </Text>
                  <Text size="sm" style={{ opacity: 0.58, lineHeight: 1.65, fontFamily: GROTESK }}>
                    {step.body}
                  </Text>
                </Box>
              ))}
            </SimpleGrid>
          </Stack>
        </Container>
      </Box>

      {/* ── What we screen for ──────────────────────────────────────── */}
      <Box id="screening" py={{ base: 56, md: 80 }}>
        <Container size="lg">
          <Stack gap={40}>
            <Stack gap={8} align="center" ta="center">
              <Text className="neo-eyebrow">What we screen for</Text>
              <Text className="neo-display" style={{ fontSize: 'clamp(1.6rem, 3.5vw, 2.3rem)', color: 'var(--neo-ink)' }}>
                Two screens running today.
              </Text>
              <Text size="sm" style={{ opacity: 0.55, maxWidth: 540, lineHeight: 1.7, fontFamily: GROTESK }}>
                We list what works now and what does not. A model that is not ready
                cannot be selected in the console, so nobody attaches a scan that
                will never be read.
              </Text>
            </Stack>

            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
              {LIVE_MODELS.map((m) => (
                <Box key={m.name} className="neo-card neo-lift" p="lg">
                  <Group justify="space-between" align="flex-start" mb="xs">
                    <Text fw={600} size="md" style={{ color: 'var(--neo-ink)', fontFamily: GROTESK }}>
                      {m.name}
                    </Text>
                    <Badge size="sm" variant="light" color="clinical" radius={3}>
                      Live
                    </Badge>
                  </Group>
                  <Text size="sm" fw={600} mb={8} style={{ color: 'var(--neo-accent-deep)', fontFamily: GROTESK }}>
                    {m.finds}
                  </Text>
                  <Text size="sm" style={{ opacity: 0.58, lineHeight: 1.65, fontFamily: GROTESK }}>
                    {m.detail}
                  </Text>
                </Box>
              ))}
            </SimpleGrid>

            <Box className="neo-card" p="lg">
              <Text fw={600} size="sm" mb={6} style={{ color: 'var(--neo-ink)', fontFamily: GROTESK }}>
                In development
              </Text>
              <Text size="sm" mb="sm" style={{ opacity: 0.58, lineHeight: 1.65, fontFamily: GROTESK }}>
                These are built into the intake form but produce no score yet. They are
                shown as unavailable rather than hidden, so you know what is coming.
              </Text>
              <Group gap="xs">
                {COMING.map((c) => (
                  <Badge key={c} size="sm" variant="outline" color="gray" radius={3}>
                    {c}
                  </Badge>
                ))}
              </Group>
            </Box>
          </Stack>
        </Container>
      </Box>

      {/* ── Tiers ───────────────────────────────────────────────────── */}
      <Box id="tiers" py={{ base: 56, md: 80 }} className="neo-steps-band">
        <Container size="lg">
          <Stack gap={36}>
            <Stack gap={8} align="center" ta="center">
              <Text className="neo-eyebrow">What you get back</Text>
              <Text className="neo-display" style={{ fontSize: 'clamp(1.6rem, 3.5vw, 2.3rem)', color: 'var(--neo-ink)' }}>
                A score, a band, and a recommended action.
              </Text>
              <Text size="sm" style={{ opacity: 0.55, maxWidth: 520, lineHeight: 1.7, fontFamily: GROTESK }}>
                Your underwriter always makes the call. The platform never issues or
                declines a policy on its own.
              </Text>
            </Stack>

            <Box className="neo-card" p={0} style={{ overflow: 'hidden' }}>
              <Table.ScrollContainer minWidth={620}>
                <Table verticalSpacing="md" horizontalSpacing="lg">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th style={{ fontFamily: GROTESK }}>Score</Table.Th>
                      <Table.Th style={{ fontFamily: GROTESK }}>Plan</Table.Th>
                      <Table.Th style={{ fontFamily: GROTESK }}>Recommendation</Table.Th>
                      <Table.Th style={{ fontFamily: GROTESK }}>Who signs it off</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {TIERS.map((t) => (
                      <Table.Tr key={t.name}>
                        <Table.Td style={{ fontFamily: GROTESK, fontWeight: 600 }}>{t.band}</Table.Td>
                        <Table.Td style={{ fontFamily: GROTESK }}>{t.name}</Table.Td>
                        <Table.Td style={{ fontFamily: GROTESK, opacity: 0.7 }}>{t.action}</Table.Td>
                        <Table.Td style={{ fontFamily: GROTESK, opacity: 0.7 }}>{t.who}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Box>
          </Stack>
        </Container>
      </Box>

      {/* ── What you get ────────────────────────────────────────────── */}
      <Box py={{ base: 56, md: 80 }}>
        <Container size="lg">
          <Stack gap={40}>
            <Stack gap={8} align="center" ta="center">
              <Text className="neo-eyebrow">Why it holds up</Text>
              <Text className="neo-display" style={{ fontSize: 'clamp(1.6rem, 3.5vw, 2.3rem)', color: 'var(--neo-ink)' }}>
                Built to be questioned.
              </Text>
            </Stack>

            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
              {WHAT_YOU_GET.map((f) => (
                <Box key={f.title} className="neo-card neo-lift" p="lg">
                  <Text fw={600} size="md" mb={8} style={{ color: 'var(--neo-ink)', fontFamily: GROTESK }}>
                    {f.title}
                  </Text>
                  <Text size="sm" style={{ opacity: 0.58, lineHeight: 1.7, fontFamily: GROTESK }}>
                    {f.body}
                  </Text>
                </Box>
              ))}
            </SimpleGrid>
          </Stack>
        </Container>
      </Box>

      {/* ── Limits ──────────────────────────────────────────────────── */}
      <Box id="limits" py={{ base: 48, md: 64 }} className="neo-steps-band">
        <Container size="md">
          <Stack gap="md" ta="center" align="center">
            <Text className="neo-eyebrow">What this is not</Text>
            <Text size="sm" style={{ opacity: 0.68, maxWidth: 620, lineHeight: 1.8, fontFamily: GROTESK, color: 'var(--neo-ink)' }}>
              This is research software. It is not a medical device, it is not
              clinically validated, and it is not approved by any regulator. It does
              not diagnose anyone. The chest model has only been tested on one
              hospital's data, so its accuracy elsewhere is unknown, and the console
              says so on every score it produces. Use it to decide where an
              underwriter should look, not to decide who gets cover.
            </Text>
          </Stack>
        </Container>
      </Box>

      {/* ── CTA ─────────────────────────────────────────────────────── */}
      <Box className="neo-cta-band" py={{ base: 72, md: 96 }}>
        <Container size="md">
          <Stack gap="lg" align="center" ta="center">
            <Text className="neo-display" style={{ fontSize: 'clamp(1.8rem, 4vw, 2.9rem)' }}>
              See what your evidence <span className="neo-underline">already says.</span>
            </Text>
            <Text style={{ opacity: 0.6, maxWidth: 440, fontSize: '0.9rem', lineHeight: 1.7, fontFamily: GROTESK, color: '#fff' }}>
              Sign in and put a scan through the console.
            </Text>
            <Box className="neo-press">
              <Button
                component={Link}
                to={ctaTo}
                size="lg"
                radius={4}
                rightSection={<IconArrowRight size={17} />}
                style={{
                  background: 'rgba(255,255,255,0.12)',
                  border: '1px solid rgba(255,255,255,0.24)',
                  fontWeight: 600,
                  fontFamily: GROTESK,
                  paddingInline: '2rem',
                  color: '#fff',
                }}
              >
                Open the console
              </Button>
            </Box>
          </Stack>
        </Container>
      </Box>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      <Box style={{ borderTop: '1px solid var(--neo-border)' }} py="lg">
        <Container size="lg">
          <Group justify="space-between" wrap="wrap">
            <Text size="sm" fw={600} style={{ color: 'var(--neo-ink)', opacity: 0.45, fontFamily: GROTESK }}>
              HomelanderAI. Underwriting decision support.
            </Text>
            <Text size="sm" fw={500} style={{ color: 'var(--neo-ink)', opacity: 0.35, fontFamily: GROTESK }}>
              {new Date().getFullYear()} HomelanderAI
            </Text>
          </Group>
          <Text size="xs" mt="md" style={{ opacity: 0.35, maxWidth: 680, lineHeight: 1.65, color: 'var(--neo-ink)', fontFamily: GROTESK }}>
            Research software. Not a medical device, not clinically validated, and not
            approved by any regulatory body. Every output is a recommendation for a
            licensed underwriter to review. The platform does not diagnose and never
            issues an automated denial.
          </Text>
        </Container>
      </Box>
    </Box>
  )
}
