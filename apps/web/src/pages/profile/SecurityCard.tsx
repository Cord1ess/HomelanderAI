import { Alert, Button, Card, Divider, Group, PasswordInput, Stack, Text } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconCheck, IconKey, IconLock, IconShield, IconShieldCheck } from '@tabler/icons-react'
import { useState } from 'react'

import { changePassword } from '../../api/client'

export function SecurityCard() {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordLoading, setPasswordLoading] = useState(false)

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!currentPassword) {
      notifications.show({
        title: 'Missing current password',
        message: 'Please enter your current account password.',
        color: 'red',
      })
      return
    }

    if (newPassword.length < 8) {
      notifications.show({
        title: 'Password too short',
        message: 'New password must be at least 8 characters long.',
        color: 'red',
      })
      return
    }

    if (newPassword !== confirmPassword) {
      notifications.show({
        title: 'Passwords do not match',
        message: 'Please ensure new password and confirmation match.',
        color: 'red',
      })
      return
    }

    setPasswordLoading(true)
    try {
      await changePassword({ currentPassword, newPassword })
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      notifications.show({
        title: 'Security credentials updated',
        message: 'Your account password has been updated successfully.',
        color: 'teal',
        icon: <IconCheck size={16} />,
      })
    } catch (err) {
      notifications.show({
        title: 'Password update failed',
        message: err instanceof Error ? err.message : 'Could not update password.',
        color: 'red',
      })
    } finally {
      setPasswordLoading(false)
    }
  }

  return (
    <Card>
      <Group justify="space-between" mb="xs">
        <Text fw={600} size="sm">
          Security & Access Credentials
        </Text>
        <IconShieldCheck size={16} />
      </Group>
      <Divider mb="sm" />

      <form onSubmit={handlePasswordSubmit}>
        <Stack gap="sm">
          <PasswordInput
            label="Current password"
            placeholder="••••••••"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.currentTarget.value)}
            leftSection={<IconLock size={14} />}
          />
          <PasswordInput
            label="New password"
            placeholder="Min. 8 characters"
            value={newPassword}
            onChange={(e) => setNewPassword(e.currentTarget.value)}
            leftSection={<IconKey size={14} />}
          />
          <PasswordInput
            label="Confirm new password"
            placeholder="Repeat new password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.currentTarget.value)}
            leftSection={<IconKey size={14} />}
          />

          <Button
            type="submit"
            variant="light"
            color="clinical"
            fullWidth
            loading={passwordLoading}
            mt="xs"
          >
            Update password
          </Button>
        </Stack>
      </form>

      <Alert
        mt="md"
        color="teal"
        variant="light"
        icon={<IconShield size={16} />}
        title="Your session"
      >
        <Text size="xs">
          You are signed in with a cookie only this browser holds; it expires on its own.
          Everything you see is filtered to your company: no screen or request can show
          another company's applications.
        </Text>
      </Alert>
    </Card>
  )
}
