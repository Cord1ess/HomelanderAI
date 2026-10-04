import {
  Alert,
  Badge,
  Box,
  Button,
  Code,
  Collapse,
  Group,
  Image,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  UnstyledButton,
} from '@mantine/core'
import { Dropzone } from '@mantine/dropzone'
import { notifications } from '@mantine/notifications'
import { IconAlertTriangle, IconFileUpload, IconFlask, IconX } from '@tabler/icons-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { getModels, tryModel, type BenchResult, type BenchRun } from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { TierBadge, type Tier } from '../../components/TierBadge'
import { ModelFieldControls } from '../intake/ModelFields'
import { declaredHistory, MODELS, type ModelValues, type Scalar } from '../intake/models'

/**
 * The owner's model test bench: pick a model, give it a test, see what it says.
 *
 * Nothing is stored and no application is made. The same model functions run
 * as for a real application, so the score here is the score an application
 * would get. A file the model does not read is still run, with a warning: a
 * confidently wrong answer is part of what testing is for.
 */
export function ModelBenchPage() {
  const { data: catalogue = [] } = useQuery({ queryKey: ['models'], queryFn: getModels })
  const [picked, setPicked] = useState<string | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [values, setValues] = useState<Record<string, ModelValues>>({})
  const [dob, setDob] = useState('')
  const [sex, setSex] = useState<string | null>(null)
  const [result, setResult] = useState<BenchResult | null>(null)

  const def = MODELS.find((m) => m.id === picked) ?? null
  const info = catalogue.find((m) => m.id === picked)

  const run = useMutation({
    mutationFn: () =>
      tryModel(picked!, {
        files,
        // Shaped as an application's answers would be, so a rule that reads
        // them reads the same keys.
        values: def ? ((declaredHistory([def.id], values)[def.id] ?? {}) as Record<string, unknown>) : {},
        dateOfBirth: dob || undefined,
        sex,
      }),
    onSuccess: setResult,
    onError: (e) => notifications.show({ title: 'The test did not run', message: (e as Error).message, color: 'red' }),
  })

  const choose = (id: string) => {
    setPicked(id)
    setFiles([])
    setResult(null)
  }
  const setField = (modelId: string, key: string, value: Scalar) =>
    setValues((p) => ({ ...p, [modelId]: { ...(p[modelId] ?? {}), [key]: value } }))
  const toggleSet = (modelId: string, key: string, value: string) =>
    setValues((p) => {
      const list = (p[modelId]?.[key] as string[]) ?? []
      return {
        ...p,
        [modelId]: { ...(p[modelId] ?? {}), [key]: list.includes(value) ? list.filter((v) => v !== value) : [...list, value] },
      }
    })

  const needsFile = Boolean(def?.upload)
  const canRun = Boolean(picked) && info?.available && (!needsFile || files.length > 0)

  return (
    <Stack gap="md" maw={1180}>
      <PageHeader screen="bench" />

      <Text fw={700} size="sm">
        1. Choose a model
      </Text>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
        {catalogue.map((m) => (
          <UnstyledButton
            key={m.id}
            onClick={() => m.available && choose(m.id)}
            disabled={!m.available}
            p="sm"
            style={{
              border: `1.5px solid ${picked === m.id ? 'var(--neo-forest)' : 'var(--neo-border-mid)'}`,
              background: picked === m.id ? 'var(--neo-accent-soft)' : 'var(--neo-card)',
              borderRadius: 8,
              opacity: m.available ? 1 : 0.55,
              cursor: m.available ? 'pointer' : 'not-allowed',
            }}
          >
            <Group justify="space-between" wrap="nowrap" align="flex-start">
              <div>
                <Text size="sm" fw={700}>
                  {m.label}
                </Text>
                <Text size="xs" c="dimmed">
                  Reads {m.evidence} · screens for {m.screensFor}
                </Text>
              </div>
              <Badge size="xs" variant="light" color={m.available ? 'teal' : 'gray'} style={{ minWidth: 'max-content' }}>
                {m.available ? (m.armVersion ?? 'ready') : 'not available'}
              </Badge>
            </Group>
          </UnstyledButton>
        ))}
      </SimpleGrid>

      {picked && def && (
        <Paper p="md" bd="1px solid var(--neo-border-mid)">
          <Text fw={700} size="sm" mb={4}>
            2. Give it a test
          </Text>
          {info?.validation && (
            <Text size="xs" c="yellow.7" mb="sm">
              {info.validation}
            </Text>
          )}
          {needsFile && (
            <>
              <Dropzone
                onDrop={(dropped) => setFiles((p) => [...p, ...dropped])}
                multiple
                maxSize={50 * 1024 * 1024}
              >
                <Group justify="center" gap="md" py="md" style={{ pointerEvents: 'none' }}>
                  <IconFileUpload size={26} style={{ color: 'var(--neo-accent)' }} />
                  <div>
                    <Text size="sm" fw={600}>
                      Drop a test file here, or click to choose
                    </Text>
                    <Text size="xs" c="dimmed">
                      {def.upload?.instruction}. Several files are each read on their own
                      {def.id === 'mirai' ? '; the mammogram model reads all four views together' : ''}.
                    </Text>
                  </div>
                </Group>
              </Dropzone>
              {files.length > 0 && (
                <Group gap="xs" mt="xs">
                  {files.map((f, i) => (
                    <Badge
                      key={`${f.name}-${i}`}
                      variant="light"
                      color="gray"
                      rightSection={
                        <IconX size={12} style={{ cursor: 'pointer' }} onClick={() => setFiles((p) => p.filter((_, j) => j !== i))} />
                      }
                    >
                      {f.name}
                    </Badge>
                  ))}
                </Group>
              )}
            </>
          )}

          {(def.fields.length > 0 || def.id === 'cxr_lung') && (
            <Box mt="md">
              <Text size="xs" fw={600} c="dimmed" tt="uppercase" mb="xs">
                Answers the model or the scoring reads
              </Text>
              <ModelFieldControls model={def} values={values[def.id] ?? {}} setField={setField} toggleSet={toggleSet} />
            </Box>
          )}
          <Group mt="md" gap="sm" align="flex-end">
            <TextInput label="Date of birth" type="date" value={dob} onChange={(e) => setDob(e.currentTarget.value)} w={180} size="xs" />
            <Select label="Sex" data={['Female', 'Male']} value={sex} onChange={setSex} clearable w={140} size="xs" />
            <Box style={{ flex: 1 }} />
            <Button leftSection={<IconFlask size={16} />} onClick={() => run.mutate()} loading={run.isPending} disabled={!canRun}>
              Run the test
            </Button>
          </Group>
        </Paper>
      )}

      {result && <Results result={result} />}
    </Stack>
  )
}

function Results({ result }: { result: BenchResult }) {
  const runs = result.runs ?? []
  return (
    <Stack gap="sm">
      <Group justify="space-between" align="flex-end">
        <div>
          <Text fw={700} size="sm">
            3. What it said
          </Text>
          <Text size="xs" c="dimmed">
            {result.modelName} {result.version}
          </Text>
        </div>
        {result.crs != null && (
          <Paper p="sm" bd="1px solid var(--neo-border-mid)">
            <Group gap="sm">
              <div>
                <Text size="xs" c="dimmed">
                  As an application's overall score
                </Text>
                <Text fw={700} size="xl" ff="monospace">
                  {result.crs.toFixed(1)}
                </Text>
              </div>
              {result.tier && <TierBadge tier={result.tier as Tier} />}
            </Group>
          </Paper>
        )}
      </Group>
      {runs.map((r, i) => (
        <RunCard key={i} run={r} />
      ))}
    </Stack>
  )
}

function RunCard({ run }: { run: BenchRun }) {
  const [open, setOpen] = useState(false)
  const images = run.images ?? []
  // What the arm says about its map: what it shows, or why none was drawn.
  const heatmap = (run.details as { heatmap?: { note?: string; reason?: string | null } } | null)?.heatmap
  return (
    <Paper p="md" bd={`1px solid ${run.error ? 'var(--neo-danger)' : 'var(--neo-border-mid)'}`}>
      <Group justify="space-between" align="flex-start">
        <div>
          <Text fw={600} size="sm">
            {run.fileName ?? 'The typed values'}
          </Text>
          {run.identifiedAs && (
            <Text size="xs" c="dimmed">
              Identified as {run.identifiedAs}
            </Text>
          )}
        </div>
        <Group gap="lg">
          <div>
            <Text size="xs" c="dimmed">
              Score (0–100)
            </Text>
            <Text fw={700} size="xl" ff="monospace">
              {run.score != null ? run.score.toFixed(1) : '—'}
            </Text>
          </div>
          <div>
            <Text size="xs" c="dimmed">
              Raw output
            </Text>
            <Text fw={600} ff="monospace">
              {run.rawScore != null ? run.rawScore.toFixed(4) : '—'}
            </Text>
          </div>
          <div>
            <Text size="xs" c="dimmed">
              Took
            </Text>
            <Text fw={600} ff="monospace">
              {(run.durationMs / 1000).toFixed(2)} s
            </Text>
          </div>
        </Group>
      </Group>
      {!run.modelReadsIt && (
        <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={16} />} mt="sm" p="xs">
          <Text size="xs">
            This model does not read {run.identifiedAs ?? 'this kind of file'}. An application would never send it here;
            the score above is what it says when it is given the wrong thing.
          </Text>
        </Alert>
      )}
      {run.error && (
        <Alert color="red" variant="light" mt="sm" p="xs">
          <Text size="xs">{run.error}</Text>
        </Alert>
      )}
      {images.length > 0 && (
        <Group mt="sm" gap="sm">
          {images.map((src, i) => (
            <Image key={i} src={src} alt="What the model drew" h={220} w="auto" fit="contain" radius="sm" />
          ))}
        </Group>
      )}
      {heatmap && (heatmap.note || heatmap.reason) && (
        <Text size="xs" c="dimmed" mt="xs">
          {images.length > 0 ? heatmap.note : heatmap.reason}
        </Text>
      )}
      <Button size="compact-xs" variant="subtle" mt="sm" onClick={() => setOpen((o) => !o)}>
        {open ? 'Hide the details' : 'Show everything the model returned'}
      </Button>
      <Collapse expanded={open}>
        <Code block mt="xs" style={{ maxHeight: 360, overflow: 'auto', fontSize: 11 }}>
          {JSON.stringify(run.details ?? {}, null, 2)}
        </Code>
      </Collapse>
    </Paper>
  )
}
