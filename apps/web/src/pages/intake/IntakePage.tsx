import {
  Badge,
  Box,
  Button,
  Checkbox,
  Container,
  Divider,
  Group,
  NumberInput,
  Paper,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  rem,
} from '@mantine/core'
import { useState } from 'react'
/**
 * Intake form — data entry with the client sitting opposite.
 *
 * ONE scrolling page with sections, submitted once at the end. Not a wizard:
 * operators jump around and clients correct themselves, so nothing may be
 * lost between steps. A sticky "n/4 sections complete" hint, one submit.
 *
 * TODO: `POST /api/applications` as `multipart/form-data` in one request; real
 * progress during upload; disable submit while in flight; confirmation panel on
 * success.
 */

function SectionTitle({ n, children }: { n: string; children: string }) {
  return (
    <Group gap="xs">
      <Badge color="clinical" variant="light" radius="sm">
        {n}
      </Badge>
      <Title order={3}>{children}</Title>
    </Group>
  )
}

export function IntakePage() {
  // Section completion drives the sticky progress hint. TODO: derive from the
  // form state, not a hardcoded count.
  const complete = 0
  const [files, setFiles] = useState<
    { name: string; size: number; type: string }[]
  >([])

  const FILE_TYPES = ['Chest X-ray', 'Lab report', 'Clinical note']

  return (
    <Container size={760}>
      <Stack gap="lg">
        {/* Sticky progress hint */}
        <Paper
          p="sm"
          withBorder
          pos="sticky"
          top={70}
          style={{ zIndex: 10 }}
          bg="var(--mantine-color-body)"
        >
          <Text size="sm" c="dimmed">
            {complete} of 4 sections complete
          </Text>
        </Paper>

        <div>
          <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: '0.12em' }}>
            New application
          </Text>
          <Title order={1}>Review a new client</Title>
          <Text size="sm" c="dimmed">
            Fill this out while the client is in front of you. One page, one
            submit.
          </Text>
        </div>

        {/* ── Section 1 · Applicant ─────────────────────────────── */}
        <Stack gap="md">
          <SectionTitle n="1">Applicant</SectionTitle>
          <TextInput
            label="Reference"
            description="The carrier's own client ID. Must be unique per tenant."
            required
            placeholder="ABC-12345"
          />
          <Group grow>
            <TextInput label="Date of birth" type="date" />
            <Select
              label="Sex"
              placeholder="Prefer not to say"
              data={['Female', 'Male', 'Other', 'Prefer not to say']}
              clearable
            />
          </Group>
        </Stack>

        <Divider my="xs" />

        {/* ── Section 2 · Coverage requested ─────────────────────── */}
        <Stack gap="md">
          <SectionTitle n="2">Coverage requested</SectionTitle>
          <Group grow>
            <Select
              label="Coverage type"
              placeholder="Select"
              required
              data={['Life', 'Health', 'Critical illness']}
            />
            <NumberInput
              label="Coverage amount (BDT)"
              placeholder="1,000,000"
              required
              thousandSeparator=","
              min={0}
            />
          </Group>
        </Stack>

        <Divider my="xs" />

        {/* ── Section 3 · Declared health ────────────────────────── */}
        <Stack gap="md">
          <SectionTitle n="3">Declared health</SectionTitle>
          <Text size="sm" c="dimmed">
            The client answers, you tick. These directly drive the risk score,
            so the wording is kept plain enough to read aloud.
          </Text>

          <Paper withBorder p="md">
            <Text fw={600} size="sm" mb="sm">
              Current symptoms
            </Text>
            <Group>
              <Checkbox label="Cough lasting more than 2 weeks" />
              <Checkbox label="Unexplained weight loss" />
              <Checkbox label="Night sweats" />
              <Checkbox label="Coughing up blood" />
              <Checkbox label="Fever" />
            </Group>
          </Paper>

          <Paper withBorder p="md">
            <Text fw={600} size="sm" mb="sm">
              Medical history
            </Text>
            <Stack>
              <Checkbox label="Previously treated for TB" />
              {/* ↳ reveal only when the above is ticked — this pair flips the outcome */}
              <Box pl="lg">
                <Checkbox label="Completed the full course of treatment" disabled />
              </Box>
              <Checkbox label="Diabetes" />
              <Checkbox label="HIV positive" />
              <Checkbox label="Someone in the household has had TB" />
              <Checkbox label="Took a course of antibiotics without improvement" />
              <Checkbox label="Current or former smoker" />
            </Stack>
          </Paper>

          <Text size="xs" c="dimmed">
            TODO: post the nested JSON shape defined in DATABASE.md §C; only
            reveal the "completed treatment" checkbox when "Previously treated
            for TB" is ticked.
          </Text>
        </Stack>

        <Divider my="xs" />

        {/* ── Section 4 · Evidence ───────────────────────────────── */}
        <Stack gap="md">
          <SectionTitle n="4">Evidence</SectionTitle>

          {/* TODO: Mantine Dropzone, click or drag, multiple files. */}
          <Paper
            withBorder
            p="xl"
            ta="center"
            style={{ borderStyle: 'dashed', cursor: 'pointer' }}
          >
            <Text fw={500}>Drop files here or click to browse</Text>
            <Text size="sm" c="dimmed" mt={4}>
              Chest X-ray required — must be .dcm, .png, or .jpg. Max 50 MB per
              file.
            </Text>
          </Paper>

          {files.length > 0 && (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>File</Table.Th>
                  <Table.Th>Size</Table.Th>
                  <Table.Th>Type</Table.Th>
                  <Table.Th w={40} />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {files.map((f) => (
                  <Table.Tr key={f.name}>
                    <Table.Td ff="monospace">{f.name}</Table.Td>
                    <Table.Td>{rem(f.size)}</Table.Td>
                    <Table.Td>
                      <Select data={FILE_TYPES} defaultValue="Chest X-ray" size="xs" />
                    </Table.Td>
                    <Table.Td>
                      <Button size="xs" variant="subtle" color="red" onClick={() => setFiles([])}>
                        Remove
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}

          <Text size="xs" c="dimmed">
            In Phase 1 only the chest X-ray is analysed. Lab reports and clinical
            notes are stored only — they are not read by the model.
          </Text>
        </Stack>

        <Divider my="xs" />

        <Button
          size="md"
          disabled
          title="Requires: reference, coverage type + amount, and at least one chest X-ray"
        >
          Submit application
        </Button>
        <Text size="xs" c="dimmed">
          Disabled until reference, coverage type and amount are filled, and at
          least one chest X-ray is attached.
        </Text>
      </Stack>
    </Container>
  )
}
