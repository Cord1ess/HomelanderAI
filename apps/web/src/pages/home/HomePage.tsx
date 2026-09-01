import {
  Anchor,
  Badge,
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
  IconBuildingBank,
  IconEye,
  IconFileCheck,
  IconHistory,
  IconShieldLock,
  IconStethoscope,
} from '@tabler/icons-react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'

import { BrandIcon } from '../../components/BrandIcon'

/**
 * Home landing — public, outside the guarded console.
 *
 * Neo-brutalist persona: a light, near-white page with hard black borders,
 * chunky offset shadows and loud clinical-teal accents. Dark ink text on the
 * light background keeps everything readable, in contrast to the dark ERP
 * console behind the login.
 */

const FEATURES = [
  {
    icon: IconStethoscope,
    title: 'TB chest X-ray screening',
    body: 'The vision arm screens chest radiographs for tuberculosis, and the declared medical history is weighed against it to reach a score.',
  },
  {
    icon: IconEye,
    title: 'Explainable Grad-CAM',
    body: 'Every recommendation ships with the heatmap and the reasoning — so the underwriter can see the evidence, not just the score.',
  },
  {
    icon: IconFileCheck,
    title: 'Write-once decisions',
    body: 'Four defined actions, no reject button. Escalation to a senior underwriter is how a declined case stays humane.',
  },
  {
    icon: IconHistory,
    title: 'Full audit trail',
    body: 'Model runs, human decisions and identities are timestamped end to end — an underwriting record you can defend.',
  },
]

const TICKER = [
  'AI decision support',
  'Human sign-off required',
  'TB chest X-ray screening',
  'Explainable Grad-CAM',
  'Full audit trail',
]

const linkStyle: CSSProperties = {
  fontWeight: 700,
  color: 'var(--neo-ink)',
  textDecorationColor: 'var(--neo-accent)',
  textUnderlineOffset: 4,
}

export function HomePage() {
  return (
    <Box className="neo-shell">
      {/* Top bar */}
      <Box style={{ borderBottom: '3px solid var(--neo-line)' }}>
        <Container size="lg" py="lg">
          <Group justify="space-between" align="center">
            <Group gap="sm" align="center">
              <Box className="neo-brand-chip neo-press" p={5}>
                <BrandIcon width={56} height={56} style={{ display: 'block' }} />
              </Box>
              <Text className="neo-display" size="xl" style={{ fontSize: '1.4rem' }}>
                HomelanderAI
              </Text>
            </Group>

            <Group gap="lg" visibleFrom="sm">
              <Anchor size="sm" style={linkStyle} href="#features">
                Features
              </Anchor>
              <Anchor size="sm" style={linkStyle} href="#features">
                How it works
              </Anchor>
              <Anchor size="sm" style={linkStyle} href="#security">
                Security
              </Anchor>
            </Group>

            <Box className="neo-press">
              <Button
                component={Link}
                to="/auth"
                size="sm"
                radius={0}
                style={{
                  border: '3px solid var(--neo-line)',
                  boxShadow: '4px 4px 0 var(--neo-ink)',
                  fontWeight: 800,
                }}
              >
                Sign in →
              </Button>
            </Box>
          </Group>
        </Container>
      </Box>

      {/* Hero */}
      <Box py={72}>
        <Container size="lg">
          <SimpleGrid cols={{ base: 1, lg: 2 }} spacing={48}>
            <Stack gap="lg">
              <div>
                <Badge
                  variant="filled"
                  color="dark"
                  radius={0}
                  size="md"
                  style={{ border: '2px solid var(--neo-ink)', boxShadow: '3px 3px 0 var(--neo-accent)' }}
                >
                  AI-assisted underwriting
                </Badge>
              </div>

              <Text
                className="home-rise home-rise-1 neo-display"
                style={{ fontSize: 'clamp(2.4rem, 6vw, 4rem)' }}
              >
                Catch early risk{' '}
                <span className="neo-underline">before</span> it becomes a claim
              </Text>

              <Text size="md" c="dark" style={{ lineHeight: 1.6, maxWidth: 520 }}>
                HomelanderAI screens chest X-rays and declared history to give
                underwriters a recommendation — and the evidence behind it —
                before a claim can expose the gap between the premium collected
                and the claim paid.
              </Text>

              <Group gap="md">
                <Box className="neo-press">
                  <Button
                    component={Link}
                    to="/auth"
                    size="lg"
                    radius={0}
                    color="clinical"
                    style={{ border: '3px solid var(--neo-ink)', boxShadow: '6px 6px 0 var(--neo-accent)', fontWeight: 800 }}
                  >
                    Sign in to the console
                  </Button>
                </Box>
                <Box className="neo-press">
                  <Button
                    component="a"
                    href="#features"
                    variant="default"
                    size="lg"
                    radius={0}
                    color="clinical"
                    rightSection={<IconArrowRight size={18} />}
                    style={{ border: '3px solid var(--neo-ink)', boxShadow: '6px 6px 0 var(--neo-ink)', fontWeight: 800, background: 'var(--neo-card)',color: 'var(--neo-ink)' }}
                  >
                    See the platform
                  </Button>
                </Box>
              </Group>

              <Group gap="xs" wrap="wrap">
                {['Human sign-off', 'PII-minimised intake', 'CPU-feasible models'].map((c) => (
                  <span key={c} className="neo-tag">
                    {c}
                  </span>
                ))}
              </Group>
            </Stack>

            <Group justify="center">
              <Box className="neo-card" p="lg">
                <Box
                  className="home-rise home-rise-3 home-float"
                  style={{ display: 'grid', placeItems: 'center' }}
                >
                  <Box className="neo-brand-chip" p={12}>
                    <BrandIcon width={232} height={232} style={{ display: 'block' }} />
                  </Box>
                </Box>
              </Box>
            </Group>
          </SimpleGrid>
        </Container>
      </Box>

      {/* Ticker */}
      <Box className="neo-ticker" py="sm">
        <Container size="lg">
          <Group gap="lg" wrap="wrap" justify="center" c="var(--neo-accent-ink)">
            {TICKER.map((t, i) => (
              <Group key={t} gap="lg" wrap="nowrap">
                {i > 0 && <Text c="var(--neo-accent-ink)" opacity={0.6}>◆</Text>}
                <Text size="sm" fw={700} tt="uppercase" style={{ letterSpacing: '0.08em' }}>
                  {t}
                </Text>
              </Group>
            ))}
          </Group>
        </Container>
      </Box>

      {/* Features */}
      <Box id="features" py={{ base: 56, md: 72 }}>
        <Container size="lg">
          <Stack gap="xl">
            <Stack gap={4} align="center" ta="center">
              <Text className="hl-eyebrow" c="var(--neo-accent)" fw={800}>
                What the console gives you
              </Text>
              <Text className="neo-display" style={{ fontSize: 'clamp(1.6rem, 4vw, 2.4rem)' }}>
                Built for the two moments that matter
              </Text>
            </Stack>

            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="lg">
              {FEATURES.map((f) => (
                <Box
                  key={f.title}
                  className="neo-card neo-lift"
                  p="lg"
                  style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem' }}
                >
                  <ThemeIcon
                    size={44}
                    radius={0}
                    color="clinical"
                    variant="filled"
                    style={{ border: '2px solid var(--neo-ink)', boxShadow: '3px 3px 0 var(--neo-ink)' }}
                  >
                    <f.icon size={22} />
                  </ThemeIcon>
                  <Text fw={800} size="md" c="var(--neo-ink)">
                    {f.title}
                  </Text>
                  <Text size="sm" c="var(--neo-ink)" opacity={0.72} style={{ lineHeight: 1.55 }}>
                    {f.body}
                  </Text>
                </Box>
              ))}
            </SimpleGrid>

            {/* Security note (id="security" target) */}
            <Group id="security" gap="xs" justify="center" mt="sm">
              <IconShieldLock size={18} color="var(--neo-accent)" />
              <Text size="sm" fw={600} c="var(--neo-ink)">
                Decisions require licensed human sign-off. Health data is
                minimised and never stored in the browser.
              </Text>
            </Group>
          </Stack>
        </Container>
      </Box>

      {/* Footer */}
      <Box style={{ borderTop: '3px solid var(--neo-line)' }} py="lg">
        <Container size="lg">
          <Group justify="space-between" wrap="wrap">
            <Group gap="xs">
              <IconBuildingBank size={18} style={{ color: 'var(--neo-ink)' }} />
              <Text size="sm" fw={700} c="var(--neo-ink)">
                HomelanderAI · Underwriting decision support
              </Text>
            </Group>
            <Text size="sm" fw={600} c="var(--neo-ink)">
              © {new Date().getFullYear()} HomelanderAI
            </Text>
          </Group>

          {/*
            This page is public and describes AI screening of medical images.
            The same disclaimer is carried by README.md and SPEC.md §10; it
            belongs where a prospective reader actually sees it.
          */}
          <Text size="xs" mt="md" c="var(--neo-ink)" opacity={0.7} maw={720}>
            Research software. Not a medical device, not clinically validated, and
            not approved by any regulatory body. Every output is a recommendation
            for a licensed underwriter to review — the platform does not diagnose
            and never issues an automated denial.
          </Text>
        </Container>
      </Box>
    </Box>
  )
}
