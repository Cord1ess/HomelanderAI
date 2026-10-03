import { Button, Group, Paper, Text, TextInput } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { getTenantSettings, updateTenantSettings } from '../../api/client'

/** The company's name, as staff see it in the console and clients in their emails. */
export function CompanyCard() {
  const queryClient = useQueryClient()
  const { data } = useQuery({ queryKey: ['tenant-settings'], queryFn: getTenantSettings })
  const [name, setName] = useState<string | null>(null)
  const value = name ?? data?.name ?? ''

  const save = useMutation({
    mutationFn: () => updateTenantSettings({ name: value.trim() }),
    onSuccess: async (updated) => {
      queryClient.setQueryData(['tenant-settings'], updated)
      void queryClient.invalidateQueries({ queryKey: ['tenant-settings-history'] })
      setName(null)
      // The console's header reads the name from the session.
      await queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
      notifications.show({ title: 'Saved', message: `The company is now called ${updated.name}.`, color: 'teal' })
    },
    onError: (e) => notifications.show({ title: 'Could not save', message: (e as Error).message, color: 'red' }),
  })

  return (
    <Paper p="md" bd="1px solid var(--mantine-color-default-border)">
      <Text fw={600} size="sm">
        Company name
      </Text>
      <Text size="xs" c="dimmed" mb="sm">
        Shown at the top of the console for everyone at your company.
      </Text>
      <Group align="flex-end" gap="sm">
        <TextInput
          style={{ flex: 1 }}
          value={value}
          onChange={(e) => setName(e.currentTarget.value)}
          placeholder="Your company's name"
          maxLength={120}
        />
        <Button
          onClick={() => save.mutate()}
          loading={save.isPending}
          disabled={!data || value.trim().length < 2 || value.trim() === data.name}
        >
          Save
        </Button>
      </Group>
    </Paper>
  )
}
