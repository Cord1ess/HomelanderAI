import { ActionIcon, Alert, Badge, Box, Button, Group, Stack, Table, Text, TextInput, Tooltip } from '@mantine/core'
import { IconArrowRight, IconLock, IconPlus, IconSearch } from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { type Client, getClients } from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { Stat } from '../../components/Stat'
import { StatusBadge } from '../../components/StatusBadge'
import { EmptyState, ErrorState } from '../../components/states'
import { TierBadge, type Tier } from '../../components/TierBadge'
import { useAuth } from '../../context/AuthContext'
import { RequestAccessModal } from './RequestAccess'

/**
 * Clients: everyone who has applied through this company, one row each, with
 * where their latest application stands. The queue is about applications;
 * this is about people, and it is where their portal sign-in is found again.
 *
 * A client's personal details are the company owner's. Anyone else sees a
 * name and a reference, and clicking a client asks the owner, with a reason.
 */

const canSee = (c: Client) => c.access === 'full' || c.access === 'granted'

function Hidden() {
  return (
    <Group gap={4} wrap="nowrap" style={{ color: 'var(--neo-muted)' }}>
      <IconLock size={12} />
      <Text span fz="xs">
        Hidden
      </Text>
    </Group>
  )
}

function AccessBadge({ client }: { client: Client }) {
  if (client.access === 'granted' && client.accessUntil) {
    const until = new Date(client.accessUntil).toLocaleString(undefined, {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    })
    return (
      <Badge size="xs" variant="light" color="teal" mt={4} style={{ minWidth: 'max-content' }}>
        Open until {until}
      </Badge>
    )
  }
  if (client.access === 'pending') {
    return (
      <Badge size="xs" variant="light" color="orange" mt={4} style={{ minWidth: 'max-content' }}>
        Asked: waiting
      </Badge>
    )
  }
  if (client.access === 'declined') {
    return (
      <Badge size="xs" variant="light" color="gray" mt={4} style={{ minWidth: 'max-content' }}>
        Request declined
      </Badge>
    )
  }
  return null
}

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
  const { user } = useAuth()
  const isOwner = user?.role === 'admin'
  const [asking, setAsking] = useState<Client | null>(null)
  const [query, setQuery] = useState('')
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['clients', query],
    queryFn: () => getClients(query || undefined),
    placeholderData: keepPreviousData,
  })
  const rows = data ?? []
  const withPortal = rows.filter((c) => c.portalId).length
  const hidden = rows.filter((c) => !canSee(c)).length
  const decided = rows.filter((c) => c.latestStatus === 'decided').length
  const waiting = rows.filter((c) => c.latestStatus && c.latestStatus !== 'decided').length

  return (
    <Stack gap="md">
      <PageHeader
        screen="clients"
        actions={
          user?.role !== 'medical_professional' && (
            <Button component={Link} to="/applications/new" size="xs" leftSection={<IconPlus size={14} />}>
              New application
            </Button>
          )
        }
      >
        <Group gap="xs" grow>
          <Stat label="Clients" value={rows.length} />
          <Stat label="With a decision" value={decided} color="teal" />
          <Stat label="Waiting" value={waiting} color="orange" hint="Latest application not yet decided" />
          {isOwner ? (
            <Stat label="Portal sign-ins" value={withPortal} hint="Clients who can follow their application" />
          ) : (
            <Stat label="Details hidden" value={hidden} hint="Click a client to ask to see them" />
          )}
        </Group>
      </PageHeader>

      {!isOwner && (
        <Alert variant="light" color="gray" icon={<IconLock size={16} />} p="sm">
          <Text size="sm">
            Contact details, portal sign-ins and test results are only shown to the company owner.
            Click a client to ask the administrator to see theirs, and say why.
          </Text>
        </Alert>
      )}

      <RequestAccessModal client={asking} onClose={() => setAsking(null)} />

      <TextInput
        size="xs"
        placeholder={isOwner ? 'Search by name, reference, phone or email' : 'Search by name or reference'}
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
                  const visible = canSee(c)
                  const href = `/clients/${c.id}`
                  const open = () => (visible ? navigate(href) : setAsking(c))
                  return (
                    <Table.Tr key={c.id} className="queue-row" data-openable onClick={open}>
                      <Table.Td>
                        <Text fz="sm" fw={600}>{c.name ?? '—'}</Text>
                        <Text fz="xs" ff="monospace" style={{ color: 'var(--neo-muted)' }}>{c.reference}</Text>
                        <AccessBadge client={c} />
                      </Table.Td>
                      <Table.Td fz="sm">
                        {visible ? (
                          <>
                            <div>{c.phone ?? '—'}</div>
                            {c.email && <Text fz="xs" style={{ color: 'var(--neo-muted)' }}>{c.email}</Text>}
                          </>
                        ) : (
                          <Hidden />
                        )}
                      </Table.Td>
                      <Table.Td fz="sm" ff="monospace">
                        {!visible ? (
                          <Hidden />
                        ) : (
                          c.portalId ?? <Text span fz="xs" style={{ color: 'var(--neo-muted)' }}>none</Text>
                        )}
                      </Table.Td>
                      <Table.Td fz="sm">
                        {!visible ? (
                          <Hidden />
                        ) : (
                          <>
                            {c.coverageAmount ? formatTaka(c.coverageAmount) : '—'}
                            {c.coverageType && (
                              <Text fz="xs" style={{ color: 'var(--neo-muted)' }}>{c.coverageType}</Text>
                            )}
                          </>
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
                        {visible ? (
                          <Tooltip label="Open the client's profile" withArrow>
                            <ActionIcon variant="light" component={Link} to={href} aria-label={`Open ${c.reference}`}>
                              <IconArrowRight size={16} />
                            </ActionIcon>
                          </Tooltip>
                        ) : (
                          <Tooltip label="Request to view this client's details" withArrow>
                            <ActionIcon
                              variant="light"
                              color="gray"
                              onClick={() => setAsking(c)}
                              aria-label={`Request to view ${c.reference}`}
                            >
                              <IconLock size={16} />
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
