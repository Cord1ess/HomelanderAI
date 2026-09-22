import {
  Alert,
  Badge,
  Box,
  Button,
  Group,
  Image,
  Loader,
  Modal,
  Select,
  Stack,
  Text,
} from '@mantine/core'
import { IconAlertTriangle } from '@tabler/icons-react'

import type { ClassifiedFile, ClassifyResponse } from '../../api/client'

/**
 * The checkpoint between "submit" and anything being scored.
 *
 * Every file is shown with what the platform thinks it is, why, and which model
 * would read it. The operator confirms or corrects each row before a single
 * model runs.
 *
 * This exists because a model handed the wrong document does not decline. The
 * retina arm returns 98.8 out of 100 on a chest X-ray, with no error and no
 * sign anything went wrong, so a misrouted file produces a confident wrong
 * score rather than a visible failure. Automatic routing alone cannot be
 * trusted with that; a person looking at a thumbnail can.
 *
 * Two rules the screen enforces:
 *  - Unrecognised files block submission. If "not recognised" could be waved
 *    through, the safeguard is gone on the first rushed afternoon.
 *  - The reason is always shown. A proposal nobody can question is one nobody
 *    can correct, and the corrections are what will train a real classifier.
 */

export interface EvidenceReviewProps {
  opened: boolean
  /** Null while classification is still running. */
  result: ClassifyResponse | null
  /** Operator corrections, keyed by filename. */
  overrides: Record<string, string>
  onOverride: (filename: string, kind: string) => void
  onConfirm: () => void
  onCancel: () => void
  submitting: boolean
}

export function EvidenceReview({
  opened,
  result,
  overrides,
  onOverride,
  onConfirm,
  onCancel,
  submitting,
}: EvidenceReviewProps) {
  const files = result?.files ?? []
  const choices = result?.choices ?? []

  const kindOf = (f: ClassifiedFile) => overrides[f.filename] ?? f.kind
  // A row is unresolved while it is still "unknown", whether that came from the
  // classifier or the operator has not picked yet.
  const unresolved = files.filter((f) => kindOf(f) === 'unknown')
  const ready = result !== null && unresolved.length === 0

  const armsFor = (kind: string) => choices.find((c) => c.kind === kind)?.arms ?? []

  return (
    <Modal
      opened={opened}
      onClose={onCancel}
      title="Check what each document is"
      size="lg"
      closeOnClickOutside={!submitting}
    >
      <Stack gap="md">
        <Text size="sm" c="dimmed">
          The models cannot tell when they have been given the wrong kind of
          document. Confirm each one before scoring starts.
        </Text>

        {result === null && (
          <Group gap="sm" py="lg" justify="center">
            <Loader size="sm" color="clinical" />
            <Text size="sm" c="dimmed">
              Reading the files
            </Text>
          </Group>
        )}

        {files.map((file) => {
          const kind = kindOf(file)
          const arms = armsFor(kind)
          const needsChoice = kind === 'unknown'
          const corrected = overrides[file.filename] && overrides[file.filename] !== file.kind

          return (
            <Box
              key={file.filename}
              p="sm"
              style={{
                border: needsChoice
                  ? '1px solid var(--mantine-color-yellow-7)'
                  : '1px solid var(--neo-border-mid)',
                borderRadius: 'var(--mantine-radius-sm)',
              }}
            >
              <Group align="flex-start" gap="md" wrap="nowrap">
                <Box
                  w={64}
                  h={64}
                  style={{
                    flex: 'none',
                    borderRadius: 4,
                    overflow: 'hidden',
                    background: 'var(--neo-bg)',
                    display: 'grid',
                    placeItems: 'center',
                  }}
                >
                  {file.thumbnail ? (
                    <Image src={file.thumbnail} alt="" w={64} h={64} fit="cover" />
                  ) : (
                    <Text size="xs" c="dimmed">
                      No preview
                    </Text>
                  )}
                </Box>

                <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
                  <Text size="sm" fw={600} className="hl-ellipsis">
                    {file.filename}
                  </Text>

                  <Select
                    size="xs"
                    value={kind === 'unknown' ? null : kind}
                    placeholder="Choose what this is"
                    data={choices.map((c) => ({ value: c.kind, label: c.label }))}
                    onChange={(v) => v && onOverride(file.filename, v)}
                    error={needsChoice ? 'Not recognised. Please choose.' : undefined}
                  />

                  <Group gap="xs">
                    {arms.length > 0 ? (
                      arms.map((a) => (
                        <Badge key={a} size="xs" variant="light" color="clinical">
                          {a}
                        </Badge>
                      ))
                    ) : (
                      <Badge size="xs" variant="outline" color="gray">
                        No model reads this yet
                      </Badge>
                    )}
                    {corrected && (
                      <Badge size="xs" variant="light" color="yellow">
                        Corrected
                      </Badge>
                    )}
                  </Group>

                  {/* Why the platform thinks this, so the operator can judge
                      whether the proposal is sensible rather than trusting it. */}
                  <Text size="xs" c="dimmed">
                    {file.reason}
                  </Text>
                </Stack>
              </Group>
            </Box>
          )
        })}

        {unresolved.length > 0 && (
          <Alert
            color="yellow"
            variant="light"
            icon={<IconAlertTriangle size={16} />}
            title={`${unresolved.length} ${unresolved.length === 1 ? 'file needs' : 'files need'} a choice`}
          >
            <Text size="sm">
              These could not be identified. Pick what each one is, or set it to
              Document so it is stored for the underwriter to read without being
              scored.
            </Text>
          </Alert>
        )}

        <Group justify="space-between">
          <Button variant="subtle" size="xs" onClick={onCancel} disabled={submitting}>
            Back to the form
          </Button>
          <Button size="xs" onClick={onConfirm} disabled={!ready} loading={submitting}>
            Confirm and submit
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
