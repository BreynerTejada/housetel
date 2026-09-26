import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { Tooltip } from 'radix-ui'
import type { ReactNode } from 'react'
import { Toaster } from '@/components/Toaster'
import { queryClient as defaultQueryClient } from '@/lib/query'
import { ThemeProvider } from '@/lib/theme'

/** Everything the app (and component tests) needs above the router. */
export function AppProviders({
  children,
  queryClient = defaultQueryClient,
}: {
  children: ReactNode
  queryClient?: QueryClient
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <Tooltip.Provider delayDuration={350} skipDelayDuration={150}>
          {children}
          <Toaster />
        </Tooltip.Provider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
