import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Card,
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
  IconFilePlus,
  IconKey,
  IconMail,
  IconPlus,
  IconRefresh,
  IconShieldCheck,
  IconStethoscope,
  IconUser,
  IconUserCheck,
} from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { getStaffUsers, provisionStaffUser } from '../../api/client'
import { TurnaroundCard } from './TurnaroundCard'
import { useAuth } from '../../context/AuthContext'
import type { UserRole } from '../../types/auth'

/**
 * Carrier Administrator — Staff Governance & Access Control.
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
        title: 'Operator provisioned',
        message: `${newMember.fullName} (${newMember.role}) has been added to ${tenant?.name ?? 'carrier'}.`,
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
        title: 'Provisioning failed',
        message: err instanceof Error ? err.message : 'Could not add staff account.',
        color: 'red',
      })
    },
  })

  const staffList = staff ?? []
  const underwriterCount = staffList.filter((s) => s.role === 'underwriter').length
  const seniorCount = staffList.filter((s) => s.role === 'senior_underwriter').length
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
      {/* ── Header ─────────────────────────────────────────── */}
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Group gap="xs" align="center">
            <Text size="lg" fw={700}>
              Carrier Staff & Access Governance
            </Text>
            <Badge color="orange" variant="filled" size="sm" leftSection={<IconShieldCheck size={12} />}>
              Tenant Administrator
            </Badge>
          </Group>
          <Text size="xs" c="dimmed">
            Manage operator accounts, license accreditations, and access tiers for {tenant?.name ?? 'your carrier'}
          </Text>
        </div>

        <Group gap="xs">
          <Button
            component={Link}
            to="/applications/new"
            size="xs"
            color="clinical"
            variant="light"
            leftSection={<IconFilePlus size={14} />}
          >
            New Applicant Intake
          </Button>
          <Button
            size="xs"
            color="clinical"
            leftSection={<IconPlus size={14} />}
            onClick={open}
          >
            Provision new operator
          </Button>
          <Tooltip label="Refresh directory" withArrow>
            <ActionIcon variant="light" onClick={() => void refetch()} loading={isFetching}>
              <IconRefresh size={16} />
            </ActionIcon>
          </Tooltip>
        </Group>
      </Group>

      {/* ── Tenant License & Staff Quota Strip ──────────────── */}
      <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="sm">
        <Card p="sm">
          <Text size="xs" c="dimmed" fw={600}>
            Carrier Tenant
          </Text>
          <Text fz="md" fw={700} mt={4}>
            {tenant?.name ?? 'Homelander Life Assurance'}
          </Text>
          <Badge size="xs" color="teal" variant="light" mt={4}>
            Subscription: {tenant?.subscriptionTier?.toUpperCase() ?? 'ENTERPRISE'}
          </Badge>
        </Card>

        <Card p="sm">
          <Text size="xs" c="dimmed" fw={600}>
            Licensed Underwriters
          </Text>
          <Text fz="xl" fw={700} c="clinical.4" mt={2}>
            {underwriterCount}
          </Text>
          <Text size="xs" c="dimmed">
            Frontline intake & Tier 1/2 adjudication
          </Text>
        </Card>

        <Card p="sm">
          <Text size="xs" c="dimmed" fw={600}>
            Senior Medical Officers
          </Text>
          <Text fz="xl" fw={700} c="grape.4" mt={2}>
            {seniorCount}
          </Text>
          <Text size="xs" c="dimmed">
            Mandatory Tier 3 escalation review authority
          </Text>
        </Card>

        <Card p="sm">
          <Text size="xs" c="dimmed" fw={600}>
            Tenant Administrators
          </Text>
          <Text fz="xl" fw={700} c="orange.4" mt={2}>
            {adminCount}
          </Text>
          <Text size="xs" c="dimmed">
            User provisioning & audit compliance
          </Text>
        </Card>
      </SimpleGrid>

      <TurnaroundCard />

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
                <Table.Th>Operator</Table.Th>
                <Table.Th>Email</Table.Th>
                <Table.Th>Role</Table.Th>
                <Table.Th>License Accreditation</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Member Since</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {isPending &&
                [0, 1, 2, 3].map((i) => (
                  <Table.Tr key={i}>
                    <Table.Td colSpan={6}>
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
                      {member.role === 'admin' ? (
                        <Badge color="orange" variant="filled" size="sm">
                          Administrator
                        </Badge>
                      ) : member.role === 'senior_underwriter' ? (
                        <Badge color="grape" variant="filled" size="sm">
                          Senior UW / Medical Officer
                        </Badge>
                      ) : (
                        <Badge color="clinical" variant="light" size="sm">
                          Underwriter
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td fz="xs" ff="monospace">
                      {member.licenseNumber ?? '—'}
                    </Table.Td>
                    <Table.Td>
                      <Badge color="teal" variant="dot" size="sm">
                        Active
                      </Badge>
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
      <Modal opened={opened} onClose={close} title="Provision Staff Operator Account" centered>
        <form onSubmit={handleSubmit}>
          <Stack gap="sm">
            <TextInput
              label="Operator Full Name"
              placeholder="e.g. Dr. Sabrina Vance"
              required
              value={fullName}
              onChange={(e) => setFullName(e.currentTarget.value)}
              leftSection={<IconUser size={14} />}
            />
            <TextInput
              label="Work Email Address"
              placeholder="operator@homelander.ai"
              required
              type="email"
              value={email}
              onChange={(e) => setEmail(e.currentTarget.value)}
              leftSection={<IconMail size={14} />}
            />
            <PasswordInput
              label="Initial Password"
              placeholder="Min. 8 characters"
              required
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
              leftSection={<IconKey size={14} />}
            />
            <Select
              label="Underwriting Role & Authority Tier"
              required
              value={role}
              onChange={(v) => setRole((v as UserRole) || 'underwriter')}
              data={[
                { value: 'underwriter', label: 'Underwriter (Intake & Tiers 1–2)' },
                { value: 'senior_underwriter', label: 'Senior Underwriter / Medical Officer (Tier 3 Adjudication)' },
                { value: 'admin', label: 'Administrator (Governance & Access)' },
              ]}
              leftSection={<IconUserCheck size={14} />}
            />
            <TextInput
              label="License Registration Number"
              placeholder="e.g. HL-MED-REG-8821"
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
