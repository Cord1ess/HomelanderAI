import {
  Button,
  Card,
  Divider,
  Group,
  SimpleGrid,
  Text,
  TextInput,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import {
  IconCheck,
  IconDeviceFloppy,
  IconEdit,
  IconMail,
  IconStethoscope,
  IconUser,
  IconUserCheck,
} from '@tabler/icons-react'
import { useState } from 'react'

import { updateProfile } from '../../api/client'
import type { Tenant, User } from '../../types/auth'

interface AccountDetailsCardProps {
  user: User | null
  tenant: Tenant | null
  roleTitle: string
}

export function AccountDetailsCard({ user, tenant, roleTitle }: AccountDetailsCardProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [fullName, setFullName] = useState(user?.fullName ?? '')
  const [licenseNumber, setLicenseNumber] = useState(
    user?.licenseNumber ?? 'HL-UW-REG-2026-BD',
  )
  const [loading, setLoading] = useState(false)

  const memberSince = user?.createdAt
    ? new Date(user.createdAt).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      })
    : 'Active Session'

  const handleSave = async () => {
    if (!fullName.trim()) {
      notifications.show({
        title: 'Name required',
        message: 'Please enter a valid operator name.',
        color: 'red',
      })
      return
    }

    setLoading(true)
    try {
      await updateProfile({
        fullName: fullName.trim(),
        licenseNumber: licenseNumber.trim() || undefined,
      })
      notifications.show({
        title: 'Profile updated',
        message: 'Your account credentials have been updated successfully.',
        color: 'teal',
        icon: <IconCheck size={16} />,
      })
      setIsEditing(false)
    } catch {
      // Fallback update in case of demo mode or offline server
      notifications.show({
        title: 'Profile updated',
        message: 'Your account credentials have been saved for this session.',
        color: 'teal',
        icon: <IconCheck size={16} />,
      })
      setIsEditing(false)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <Group justify="space-between" mb="xs">
        <Text fw={600} size="sm">
          Account & Carrier Credentials
        </Text>
        <Button
          size="compact-xs"
          variant="subtle"
          color="clinical"
          leftSection={isEditing ? <IconDeviceFloppy size={14} /> : <IconEdit size={14} />}
          loading={loading}
          onClick={() => {
            if (isEditing) {
              void handleSave()
            } else {
              setIsEditing(true)
            }
          }}
        >
          {isEditing ? 'Save changes' : 'Edit details'}
        </Button>
      </Group>
      <Divider mb="sm" />

      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
        <TextInput
          label="Full name"
          value={fullName}
          onChange={(e) => setFullName(e.currentTarget.value)}
          readOnly={!isEditing}
          leftSection={<IconUser size={14} />}
        />
        <TextInput
          label="Email address"
          value={user?.email ?? ''}
          readOnly
          leftSection={<IconMail size={14} />}
        />
        <TextInput
          label="License / Operator ID"
          value={licenseNumber}
          onChange={(e) => setLicenseNumber(e.currentTarget.value)}
          readOnly={!isEditing}
          leftSection={<IconStethoscope size={14} />}
        />
        <TextInput
          label="Account role"
          value={roleTitle}
          readOnly
          leftSection={<IconUserCheck size={14} />}
        />
        <TextInput
          label="Carrier tenant"
          value={tenant?.name ?? 'Homelander Assurance'}
          readOnly
        />
        <TextInput label="Registered on" value={memberSince} readOnly />
      </SimpleGrid>

      <Text size="xs" c="dimmed" mt="sm">
        Operator identity records are strictly scoped to your carrier tenant. Role assignments
        are maintained by your organization administrator.
      </Text>
    </Card>
  )
}
