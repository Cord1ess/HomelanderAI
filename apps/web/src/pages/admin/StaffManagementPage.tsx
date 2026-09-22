import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Divider,
  Group,
  Modal,
  PasswordInput,
  Select,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import {
  IconAlertCircle,
  IconCheck,
  IconKey,
  IconMail,
  IconPlus,
  IconRefresh,
  IconStethoscope,
  IconUser,
  IconUserCheck,
} from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { getStaffUsers, provisionStaffUser } from '../../api/client'
import { useAuth } from '../../context/AuthContext'
import { PageHeader } from '../../components/PageHeader'
import { Stat } from '../../components/Stat'
import { ROLE_LABEL } from '../../types/auth'
import type { UserRole } from '../../types/auth'

/**
 * Administrator — Staff Governance & Access Control.
 *
 * Dedicated admin workbench to provision underwriters, manage operator seats,
 * monitor account status, and enforce carrier underwriting compliance.
 */

export function StaffManagementPage() {
  const { tenant } = useAuth()
  const queryClient = useQueryClient()
  const [opened, { open, close }] = useDisclosure(false)

  // Provisioning form state
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('underwriter')
  const [licenseNumber, setLicenseNumber] = useState('')

  const { data: staff, isPending, isFetching, error, refetch } = useQuery({
    queryKey: ['admin', 'staff'],
    queryFn: getStaffUsers,
  })

  const provisionMutation = useMutation({
    mutationFn: provisionStaffUser,
    onSuccess: (newMember) => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'staff'] })
      notifications.show({
        title: 'Account created',
        message: `${newMember.fullName} can now sign in as ${ROLE_LABEL[newMember.role]} at ${tenant?.name ?? 'your company'}.`,
        color: 'teal',
        icon: <IconCheck size={16} />,
      })
      close()
      setFullName('')
      setEmail('')
      setPassword('')
      setLicenseNumber('')
    },
    onError: (err) => {
      notifications.show({
        title: 'Could not create the account',
        message: err instanceof Error ? err.message : 'Something went wrong.',
        color: 'red',
      })
    },
  })

  const staffList = staff ?? []
  const underwriterCount = staffList.filter((s) => s.role === 'underwriter').length
  const medicalCount = staffList.filter((s) => s.role === 'medical_professional').length
  const adminCount = staffList.filter((s) => s.role === 'admin').length

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!fullName.trim() || !email.trim() || password.length < 8) {
      notifications.show({
        title: 'Validation error',
        message: 'Please fill in all required fields (password min. 8 characters).',
        color: 'red',
      })
      return
    }

    provisionMutation.mutate({
      fullName: fullName.trim(),
      email: email.trim(),
      password,
      role,
      licenseNumber: licenseNumber.trim() || undefined,
    })
  }

  return (
    <Stack gap="md">
      <PageHeader
        screen="staff"
        actions={
          <>
            <Button size="xs" leftSection={<IconPlus size={14} />} onClick={open}>
              Add a person
            </Button>
            <Tooltip label="Refresh the list" withArrow>
              <ActionIcon variant="light" aria-label="Refresh" onClick={() => void refetch()} loading={isFetching}>
                <IconRefresh size={16} />
              </ActionIcon>
            </Tooltip>
          </>
        }
      >
        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="xs">
          <Stat label="Underwriters" value={underwriterCount} color="clinical" hint="Take applications in and decide low and moderate cases" />
          <Stat label="Medical professionals" value={medicalCount} color="grape" hint="Decide the escalated cases" />
          <Stat label="Administrators" value={adminCount} color="orange" hint="Manage staff and company settings" />
        </SimpleGrid>
      </PageHeader>

      {error && (
        <Alert color="red" variant="light" icon={<IconAlertCircle size={16} />} title="Could not load staff directory">
          {error instanceof Error ? error.message : 'Unknown error'}
        </Alert>
      )}

      {/* ── Operator Directory Table ────────────────────────── */}
      <Box
        style={{
          border: '1px solid var(--mantine-color-default-border)',
          borderRadius: 'var(--mantine-radius-sm)',
          overflow: 'hidden',
        }}
      >
        <Table.ScrollContainer minWidth={760}>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Sign-in email</Table.Th>
                <Table.Th>Role</Table.Th>
                <Table.Th>Licence number</Table.Th>
                <Table.Th>Added</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {isPending &&
                [0, 1, 2, 3].map((i) => (
                  <Table.Tr key={i}>
                    <Table.Td colSpan={5}>
                      <Skeleton height={20} />
                    </Table.Td>
                  </Table.Tr>
                ))}

              {!isPending &&
                staffList.map((member) => (
                  <Table.Tr key={member.id}>
                    <Table.Td>
                      <Group gap="xs" wrap="nowrap">
                        <IconUser size={15} color="var(--mantine-color-dimmed)" />
                        <Text fz="sm" fw={600}>
                          {member.fullName}
                        </Text>
                      </Group>
                    </Table.Td>
                    <Table.Td fz="sm" ff="monospace">
                      {member.email}
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={member.role === 'admin' ? 'orange' : member.role === 'medical_professional' ? 'grape' : 'clinical'}
                        variant={member.role === 'underwriter' ? 'light' : 'filled'}
                        size="sm"
                      >
                        {ROLE_LABEL[member.role]}
                      </Badge>
                    </Table.Td>
                    <Table.Td fz="xs" ff="monospace">
                      {member.licenseNumber ?? '—'}
                    </Table.Td>
                    <Table.Td fz="xs" c="dimmed">
                      {new Date(member.createdAt).toLocaleDateString('en-US', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      })}
                    </Table.Td>
                  </Table.Tr>
                ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Box>

      {/* ── Provisioning Modal ──────────────────────────────── */}
      <Modal opened={opened} onClose={close} title="Add a person" centered>
        <form onSubmit={handleSubmit}>
          <Stack gap="sm">
            <TextInput
              label="Full name"
              placeholder="e.g. Dr. Sabrina Vance"
              required
              value={fullName}
              onChange={(e) => setFullName(e.currentTarget.value)}
              leftSection={<IconUser size={14} />}
            />
            <TextInput
              label="Work email"
              description="What they sign in with"
              placeholder="name@yourcompany.com"
              required
              type="email"
              value={email}
              onChange={(e) => setEmail(e.currentTarget.value)}
              leftSection={<IconMail size={14} />}
            />
            <PasswordInput
              label="First password"
              description="Give it to them in person; they can change it from Your account"
              placeholder="At least 8 characters"
              required
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
              leftSection={<IconKey size={14} />}
            />
            <Select
              label="Role"
              required
              value={role}
              onChange={(v) => setRole((v as UserRole) || 'underwriter')}
              data={[
                { value: 'underwriter', label: 'Underwriter: takes applications, decides low and moderate cases' },
                { value: 'medical_professional', label: 'Medical Professional: decides escalated cases' },
                { value: 'admin', label: 'Administrator: staff accounts and company settings' },
              ]}
              leftSection={<IconUserCheck size={14} />}
            />
            <TextInput
              label="Licence number"
              description="Optional. Their professional registration, if they have one"
              placeholder="e.g. LIC-0042"
              value={licenseNumber}
              onChange={(e) => setLicenseNumber(e.currentTarget.value)}
              leftSection={<IconStethoscope size={14} />}
            />

            <Divider my="xs" />

            <Group justify="flex-end" gap="xs">
              <Button variant="default" onClick={close}>
                Cancel
              </Button>
              <Button type="submit" color="clinical" loading={provisionMutation.isPending}>
                Create account
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  )
}
