import { Box, Checkbox, Group, NumberInput, Radio, Select, SimpleGrid, Stack, Text } from '@mantine/core'

import { bool, CARDIO, HISTORY_ONCE, type ModelDef, type ModelValues, type Scalar, SYMPTOMS } from './models'

/** The questions one reader asks, as form controls. */
export function ModelFieldControls({
  model,
  values,
  setField,
  toggleSet,
}: {
  model: ModelDef
  values: ModelValues
  setField: (modelId: string, key: string, value: Scalar) => void
  toggleSet: (modelId: string, key: string, value: string) => void
}) {
  if (model.id === 'cxr_lung') {
    return (
      <CxrPanel values={values} setField={setField} toggleSet={toggleSet} />
    )
  }

  if (model.fields.length === 0) {
    return (
      <Text size="xs" c="dimmed">
        No additional questions — the {model.label} model reads the uploaded report directly.
      </Text>
    )
  }

  // Typed values and choices sit three to a row; the yes/no questions follow
  // as a list. A long panel of one field per line hid how little was asked.
  const typed = model.fields.filter((f) => f.kind !== 'checkbox')
  const ticks = model.fields.filter((f) => f.kind === 'checkbox')
  return (
    <Stack gap="sm">
      {typed.length > 0 && (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm" verticalSpacing="sm">
          {typed.map((f) =>
            f.kind === 'select' ? (
              <Select
                key={f.key}
                label={f.label}
                placeholder={f.placeholder ?? 'Select'}
                data={f.data}
                clearable
                value={typeof values[f.key] === 'string' ? (values[f.key] as string) : null}
                onChange={(v) => setField(model.id, f.key, v)}
              />
            ) : f.kind === 'number' ? (
              <NumberInput
                key={f.key}
                label={f.label}
                description={f.description}
                min={0}
                value={typeof values[f.key] === 'number' ? (values[f.key] as number) : undefined}
                onChange={(v) => setField(model.id, f.key, v === '' ? null : v)}
              />
            ) : null,
          )}
        </SimpleGrid>
      )}
      {ticks.map((f) => (
        <Checkbox
          key={f.key}
          label={f.label}
          checked={bool(values[f.key])}
          onChange={(e) => setField(model.id, f.key, e.currentTarget.checked)}
        />
      ))}
    </Stack>
  )
}

function CxrPanel({
  values,
  setField,
  toggleSet,
}: {
  values: ModelValues
  setField: (modelId: string, key: string, value: Scalar) => void
  toggleSet: (modelId: string, key: string, value: string) => void
}) {
  const modelId = 'cxr_lung'
  const sym = (values.symptoms as string[]) ?? []
  const hist = (values.history as string[]) ?? []
  const cardio = (values.cardio as string[]) ?? []

  return (
    <Stack gap="md">
      {/* Current symptoms */}
      <Box>
        <Text fw={600} size="sm" mb="xs">
          Current symptoms
        </Text>
        <Stack gap="xs">
          {SYMPTOMS.map((s) => (
            <Checkbox
              key={s.key}
              label={s.label}
              checked={sym.includes(s.key)}
              onChange={() => toggleSet(modelId, 'symptoms', s.key)}
            />
          ))}
        </Stack>
      </Box>

      {/* TB history */}
      <Box>
        <Text fw={600} size="sm" mb="xs">
          Medical history
        </Text>
        <Stack gap="xs">
          <Checkbox
            label="Previously treated for TB"
            checked={bool(values.prior_tb)}
            onChange={(e) => {
              setField(modelId, 'prior_tb', e.currentTarget.checked)
              // Clear the follow-up when the parent is un-ticked, so a stale
              // answer cannot be submitted for someone with no TB history.
              if (!e.currentTarget.checked) {
                setField(modelId, 'prior_tb_treatment_completed', null)
              }
            }}
          />
          {bool(values.prior_tb) && (
            <Box pl="lg">
              {/*
                Yes/No rather than a checkbox. An unticked box cannot say whether
                the course was not completed or the question was never asked, and
                the two mean different things: a completed course lowers the score
                by 25, an incomplete one does not. Unanswered is sent as null and
                gated at submit rather than guessed.
              */}
              <Radio.Group
                label="Completed the full course of treatment"
                value={(values.prior_tb_treatment_completed as string) ?? ''}
                onChange={(v) => setField(modelId, 'prior_tb_treatment_completed', v)}
              >
                <Group gap="lg" mt={6}>
                  <Radio value="yes" label="Yes" />
                  <Radio value="no" label="No" />
                </Group>
              </Radio.Group>
            </Box>
          )}
          {HISTORY_ONCE.map((h) => (
            <Checkbox
              key={h.key}
              label={h.label}
              checked={hist.includes(h.key)}
              onChange={() => toggleSet(modelId, 'history', h.key)}
            />
          ))}
        </Stack>
      </Box>

      {/* Cardio */}
      <Box>
        <Text fw={600} size="sm" mb="xs">
          Cardiovascular
        </Text>
        <Stack gap="xs">
          {CARDIO.map((c) => (
            <Checkbox
              key={c.key}
              label={c.label}
              checked={cardio.includes(c.key)}
              onChange={() => toggleSet(modelId, 'cardio', c.key)}
            />
          ))}
        </Stack>
      </Box>
    </Stack>
  )
}

