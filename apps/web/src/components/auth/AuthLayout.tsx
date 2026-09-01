import {
  Badge,
  Box,
  Card,
  Container,
  Group,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core'
import { IconActivity, IconCpu, IconFileText, IconStethoscope } from '@tabler/icons-react'
import type { ReactNode } from 'react'

interface AuthLayoutProps {
  children: ReactNode
}

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <Box bg="var(--mantine-color-body)" mih="100vh" py={{ base: 32, md: 80 }}>
      <Container size="lg">
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing={{ base: 32, md: 64 }} verticalSpacing={32}>
          {/* ── Left Column: Minimalist & Catchy Brand Panel ─────────────────── */}
          <Stack justify="center" gap="xl" pr={{ md: 'md' }}>
            <Stack gap="md">
              {/* Brand Logo */}
              <Group gap="xs">
                <ThemeIcon size={40} radius="md" color="clinical.5" variant="filled">
                  <IconActivity size={24} />
                </ThemeIcon>
                <Text ff="monospace" fw={700} size="xl" c="clinical.4">
                  HomelanderAI
                </Text>
                <Badge size="xs" color="clinical" radius="sm" variant="light">
                  Decision Support
                </Badge>
              </Group>

              {/* Minimalist Catchy Headline */}
              <Stack gap={6} mt="xs">
                <Title
                  order={1}
                  size="h1"
                  style={{
                    fontSize: '2.4rem',
                    lineHeight: '1.15',
                    letterSpacing: '-0.03em',
                    fontWeight: 700,
                  }}
                >
                  Precision Underwriting.
                  <br />
                  <Text
                    component="span"
                    inherit
                    variant="gradient"
                    gradient={{ from: 'clinical.3', to: 'teal.2', deg: 90 }}
                  >
                    Calibrated Risk.
                  </Text>
                </Title>

                <Text c="dimmed" size="sm" mt="xs" style={{ maxWidth: 420 }}>
                  Helps insurance underwriters review medical evidence and decide on applications.
                </Text>
              </Stack>

              {/* Minimalist Visual Feature Pills */}
              <Group gap="xs" mt="sm">
                <Paper
                  px="xs"
                  py={6}
                  radius="xl"
                  withBorder
                  bg="dark.7"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                >
                  <IconStethoscope size={14} color="var(--mantine-color-clinical-4)" />
                  <Text size="xs" fw={500}>
                    Vision AI
                  </Text>
                </Paper>

                <Paper
                  px="xs"
                  py={6}
                  radius="xl"
                  withBorder
                  bg="dark.7"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                >
                  <IconFileText size={14} color="var(--mantine-color-clinical-4)" />
                  <Text size="xs" fw={500}>
                    Clinical NLP
                  </Text>
                </Paper>

                <Paper
                  px="xs"
                  py={6}
                  radius="xl"
                  withBorder
                  bg="dark.7"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                >
                  <IconCpu size={14} color="var(--mantine-color-clinical-4)" />
                  <Text size="xs" fw={500}>
                    Actuarial Risk
                  </Text>
                </Paper>
              </Group>
            </Stack>

            {/* Quiet Footer Tagline */}
            <Text size="xs" c="dimmed" style={{ opacity: 0.6 }}>
              Human-in-the-loop audit trail • No automated denials
            </Text>
          </Stack>

          {/* ── Right Column: Auth Form Container ────────────────────────────── */}
          <Box style={{ alignSelf: 'center', width: '100%' }}>
            <Card shadow="xl" radius="lg" p={{ base: 'lg', sm: 'xl' }} withBorder bg="dark.8">
              {children}
            </Card>
          </Box>
        </SimpleGrid>
      </Container>
    </Box>
  )
}
