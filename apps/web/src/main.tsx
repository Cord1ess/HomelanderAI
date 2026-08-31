import { MantineProvider } from '@mantine/core'
import { Notifications } from '@mantine/notifications'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

// Mantine stylesheets must be imported before our own CSS so we can override.
// Add the matching import when you start using a package:
//   import '@mantine/dropzone/styles.css'
//   import '@mantine/charts/styles.css'
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import './index.css'

import { App } from './App'
import { theme } from './theme'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 5_000,
    },
  },
})

const root = document.getElementById('root')
if (!root) throw new Error('#root element is missing from index.html')

createRoot(root).render(
  <StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <Notifications position="top-right" />
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
)
