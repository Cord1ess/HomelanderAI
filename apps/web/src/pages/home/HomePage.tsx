import {
  Anchor,
  Badge,
  Box,
  Button,
  Container,
  Group,
  Paper,
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
import { Link } from 'react-router-dom'

import { BrandIcon } from '../../components/BrandIcon'

/**
 * Home landing — public, outside the guarded console.
 *
 * A modern SaaS hero: brand mark + animated keyline up top, an eyebrow →
 * headline → value prop, a pair of CTAs (sign-in, then a scroll to the
 * features), trust chips and a feature grid. Motion is subtle (rise-on-load,
 * a floating brand mark, a soft sheen) — no gradients-for-gradient's-sake.
 */

const FEATURES = [
  {
    icon: IconStethoscope,
    title: 'TB chest X-ray screening',
    body: 'The vision arm screens chest radiographs for tuberculosis while the other model arms weigh the declared history.',
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

const CHIPS = ['Decision support, human sign-off', 'PII-minimised intake', 'CPU-feasible models']

export function HomePage() {
  return (
    <Box className="home-aurora" bg="var(--mantine-color-dark-9)" mih="100vh">
      <div className="home-grid" />

      {/* Top bar */}
      <Container size="lg" py="md">
        <Group justify="space-between" align="center">
          <Group gap="sm" align="center">
            <Paper className="home-brand-chip" p={4} radius="sm" w={92}>
              <BrandIcon width={84} height={40} style={{ display: 'block' }} />
            </Paper>
            <Text fw={700} size="sm" c="gray.1">
              HomelanderAI
            </Text>
          </Group>

          <Group gap="lg" visibleFrom="sm">
            <Anchor size="sm" c="dimmed" href="#features">
              Features
            </Anchor>
            <Anchor size="sm" c="dimmed" href="#features">
              How it works
            </Anchor>
            <Anchor size="sm" c="dimmed" href="#security">
              Security
            </Anchor>
          </Group>

          <Button component={Link} to="/login" color="clinical" size="xs" radius="md">
            Sign in
          </Button>
        </Group>
      </Container>

      {/* Hero */}
      <Container size="lg" py={88}>
        <Stack align="center" gap="xl" ta="center">
          <Box className="home-rise home-rise-1 home-float">
            <Paper className="home-brand-chip home-sheen" p={10} radius="lg">
              <BrandIcon width={240} height={110} style={{ display: 'block' }} />
            </Paper>
          </Box>

          <Stack align="center" gap="sm" maw={760}>
            <Badge
              className="home-rise home-rise-2"
              color="clinical"
              variant="light"
              size="sm"
              radius="xl"
            >
              AI-assisted underwriting
            </Badge>
            <Text
              className="home-rise home-rise-2"
              fw={700}
              style={{ fontSize: 'clamp(2rem, 5vw, 3.25rem)', lineHeight: 1.08, letterSpacing: '-0.02em' }}
            >
              Catch early risk before it becomes a claim
            </Text>
            <Text className="home-rise home-rise-3" size="md" c="dimmed" maw={620} style={{ lineHeight: 1.6 }}>
              HomelanderAI screens chest X-rays and declared history to give
              underwriters a recommendation — and the evidence behind it — before a
              claim can expose the gap between premium collected and the claim paid.
            </Text>
          </Stack>

          <Group className="home-rise home-rise-4" gap="sm" justify="center">
            <Button component={Link} to="/login" color="clinical" size="md" radius="md">
              Sign in to the console
            </Button>
            <Button
              variant="default"
              size="md"
              radius="md"
              rightSection={<IconArrowRight size={16} />}
              component="a"
              href="#features"
            >
              See the platform
            </Button>
          </Group>

          <Group className="home-rise home-rise-4" gap="xs" justify="center" wrap="wrap">
            {CHIPS.map((chip) => (
              <Badge key={chip} variant="outline" color="gray" size="sm" radius="xl">
                {chip}
              </Badge>
            ))}
          </Group>
        </Stack>
      </Container>

      {/* Features */}
      <Box id="features" py={{ base: 48, md: 64 }} style={{ borderTop: '1px solid var(--mantine-color-dark-7)' }}>
        <Container size="lg">
          <Stack gap="xl">
            <Stack gap={4} align="center" ta="center">
              <Text className="hl-eyebrow" c="clinical.4">
                What the console gives you
              </Text>
              <Text fw={700} size="xl">
                Built for the two moments that matter
              </Text>
            </Stack>

            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
              {FEATURES.map((f) => (
                <Paper
                  key={f.title}
                  p="lg"
                  radius="md"
                  className="home-feature"
                  style={{ border: '1px solid var(--mantine-color-dark-6)', backgroundColor: 'var(--mantine-color-dark-8)' }}
                >
                  <Stack gap="sm">
                    <ThemeIcon size={40} radius="md" color="clinical" variant="light">
                      <f.icon size={20} />
                    </ThemeIcon>
                    <Text fw={600} size="sm">
                      {f.title}
                    </Text>
                    <Text size="xs" c="dimmed" style={{ lineHeight: 1.55 }}>
                      {f.body}
                    </Text>
                  </Stack>
                </Paper>
              ))}
            </SimpleGrid>

            {/* Security note (id="security" target) */}
            <Group id="security" gap="xs" justify="center" c="dimmed" mt="sm">
              <IconShieldLock size={16} color="var(--mantine-color-clinical-5)" />
              <Text size="xs">
                Decisions require licensed human sign-off. Health data is minimised
                and never stored in the browser.
              </Text>
            </Group>
          </Stack>
        </Container>
      </Box>

      {/* Footer */}
      <Box style={{ borderTop: '1px solid var(--mantine-color-dark-7)' }} py="lg">
        <Container size="lg">
          <Group justify="space-between">
            <Group gap="xs">
              <IconBuildingBank size={16} style={{ color: 'var(--mantine-color-dimmed)' }} />
              <Text size="xs" c="dimmed">
                HomelanderAI · Underwriting decision support
              </Text>
            </Group>
            <Text size="xs" c="dimmed">
              © {new Date().getFullYear()} HomelanderAI
            </Text>
          </Group>
        </Container>
      </Box>
    </Box>
  )
}
