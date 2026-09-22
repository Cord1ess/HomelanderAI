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
        message: 'Enter your name.',
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
        message: 'Your details have been saved.',
        color: 'teal',
        icon: <IconCheck size={16} />,
      })
      setIsEditing(false)
    } catch (err) {
      notifications.show({
        title: 'Could not save',
        message: err instanceof Error ? err.message : 'Something went wrong. Your changes were not saved.',
        color: 'red',
      })
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
          label="Licence number"
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
          label="Company"
          value={tenant?.name ?? 'Homelander Assurance'}
          readOnly
        />
        <TextInput label="Registered on" value={memberSince} readOnly />
      </SimpleGrid>

      <Text size="xs" c="dimmed" mt="sm">
        Your role is set by an administrator at your company; ask them if it needs to change.
      </Text>
    </Card>
  )
}
