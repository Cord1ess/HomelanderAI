import { ActionIcon, Badge, Box, Button, Group, Stack, Table, Text, TextInput, Tooltip } from '@mantine/core'
import { IconArrowRight, IconPlus, IconSearch } from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { getClients } from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { Stat } from '../../components/Stat'
import { StatusBadge } from '../../components/StatusBadge'
import { EmptyState, ErrorState } from '../../components/states'
import { TierBadge, type Tier } from '../../components/TierBadge'

/**
 * Clients: everyone who has applied through this company, one row each, with
 * where their latest application stands. The queue is about applications;
 * this is about people, and it is where their portal sign-in is found again.
 */

function formatTaka(value: string | number): string {
  return `৳${Math.round(Number(value)).toLocaleString('en-IN')}`
}

function formatDay(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
  })
}

export function ClientsPage() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['clients', query],
    queryFn: () => getClients(query || undefined),
    placeholderData: keepPreviousData,
  })
  const rows = data ?? []
  const withPortal = rows.filter((c) => c.portalId).length
  const decided = rows.filter((c) => c.latestStatus === 'decided').length
  const waiting = rows.filter((c) => c.latestStatus && c.latestStatus !== 'decided').length

  return (
    <Stack gap="md">
      <PageHeader
        screen="clients"
        actions={
          <Button component={Link} to="/applications/new" size="xs" leftSection={<IconPlus size={14} />}>
            New application
          </Button>
        }
      >
        <Group gap="xs" grow>
          <Stat label="Clients" value={rows.length} />
          <Stat label="With a decision" value={decided} color="teal" />
          <Stat label="Waiting" value={waiting} color="orange" hint="Latest application not yet decided" />
          <Stat label="Portal sign-ins" value={withPortal} hint="Clients who can follow their application" />
        </Group>
      </PageHeader>

      <TextInput
        size="xs"
        placeholder="Search by name, reference, phone or email"
        aria-label="Search clients"
        leftSection={<IconSearch size={14} />}
        value={query}
        onChange={(e) => setQuery(e.currentTarget.value)}
        w={320}
      />

      {error && !data && <ErrorState title="Could not load the clients" error={error} retry={() => void refetch()} />}

      {!(error && !data) && (
        <Box style={{ border: '1px solid var(--neo-border-mid)', borderRadius: 'var(--mantine-radius-sm)', overflow: 'hidden' }}>
          <Table.ScrollContainer minWidth={900}>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Client</Table.Th>
                  <Table.Th>Contact</Table.Th>
                  <Table.Th>Portal ID</Table.Th>
                  <Table.Th>Cover</Table.Th>
                  <Table.Th>Latest application</Table.Th>
                  <Table.Th>Tier</Table.Th>
                  <Table.Th>Answer promised</Table.Th>
                  <Table.Th w={56} aria-label="Open" />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {!isPending && rows.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={8} p={0}>
                      <EmptyState
                        title={query ? 'No client matches' : 'No clients yet'}
                        text={query ? 'Try a different name, reference, phone or email.' : 'Every application you take adds its client here.'}
                      />
                    </Table.Td>
                  </Table.Tr>
                )}
                {rows.map((c) => {
                  const href = c.latestApplicationId ? `/applications/${c.latestApplicationId}` : null
                  return (
                    <Table.Tr
                      key={c.id}
                      className="queue-row"
                      data-openable={href ? true : undefined}
                      onClick={href ? () => navigate(href) : undefined}
                    >
                      <Table.Td>
                        <Text fz="sm" fw={600}>{c.name ?? '—'}</Text>
                        <Text fz="xs" ff="monospace" style={{ color: 'var(--neo-muted)' }}>{c.reference}</Text>
                      </Table.Td>
                      <Table.Td fz="sm">
                        <div>{c.phone ?? '—'}</div>
                        {c.email && <Text fz="xs" style={{ color: 'var(--neo-muted)' }}>{c.email}</Text>}
                      </Table.Td>
                      <Table.Td fz="sm" ff="monospace">
                        {c.portalId ?? <Text span fz="xs" style={{ color: 'var(--neo-muted)' }}>none</Text>}
                      </Table.Td>
                      <Table.Td fz="sm">
                        {c.coverageAmount ? formatTaka(c.coverageAmount) : '—'}
                        {c.coverageType && (
                          <Text fz="xs" style={{ color: 'var(--neo-muted)' }}>{c.coverageType}</Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        {c.latestStatus ? <StatusBadge status={c.latestStatus} /> : <Text fz="xs" c="dimmed">none</Text>}
                        {c.applications > 1 && (
                          <Text fz="xs" mt={2} style={{ color: 'var(--neo-muted)' }}>{c.applications} applications</Text>
                        )}
                      </Table.Td>
                      <Table.Td>{c.latestTier ? <TierBadge tier={c.latestTier as Tier} /> : '—'}</Table.Td>
                      <Table.Td fz="sm" style={{ color: c.overdue ? 'var(--neo-danger)' : 'var(--neo-muted)' }}>
                        {c.expectedBy ? formatDay(c.expectedBy) : '—'}
                        {c.overdue && <Badge ml={6} size="xs" color="red" variant="light">Late</Badge>}
                      </Table.Td>
                      <Table.Td onClick={(e) => e.stopPropagation()}>
                        {href && (
                          <Tooltip label="Open the latest application" withArrow>
                            <ActionIcon variant="light" component={Link} to={href} aria-label={`Open ${c.reference}`}>
                              <IconArrowRight size={16} />
                            </ActionIcon>
                          </Tooltip>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  )
                })}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Box>
      )}
    </Stack>
  )
}
