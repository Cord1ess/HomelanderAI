import { Box, Tabs, Text } from '@mantine/core'
import { IconBuildingStore, IconLogin } from '@tabler/icons-react'
import { useState } from 'react'
import { LoginForm } from './LoginForm'
import { RegisterTenantForm } from './RegisterTenantForm'

export function AuthTabs() {
  const [activeTab, setActiveTab] = useState<string | null>('login')

  return (
    <Box>
      <Tabs value={activeTab} onChange={setActiveTab} variant="outline" radius="md" color="clinical">
        <Tabs.List grow mb="lg">
          <Tabs.Tab value="login" leftSection={<IconLogin size={16} />}>
            <Text fw={600} size="sm">
              Carrier Sign In
            </Text>
          </Tabs.Tab>
          <Tabs.Tab value="register" leftSection={<IconBuildingStore size={16} />}>
            <Text fw={600} size="sm">
              Onboard Carrier
            </Text>
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="login">
          <LoginForm onSwitchToRegister={() => setActiveTab('register')} />
        </Tabs.Panel>

        <Tabs.Panel value="register">
          <RegisterTenantForm onSwitchToLogin={() => setActiveTab('login')} />
        </Tabs.Panel>
      </Tabs>
    </Box>
  )
}
