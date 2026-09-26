import { lazy, Suspense, type ComponentType } from 'react'
import type { PublicWidgetProps } from '@/app/extensions'
import { ErrorBoundary } from '@/components/ErrorBoundary'

// Mounted by the public layouts; loads features/ai/public-widget.tsx only if that file exists (C9).
const loaders = import.meta.glob<{ default: ComponentType<PublicWidgetProps> }>('../../features/ai/public-widget.tsx')
const loader = Object.values(loaders)[0]
const PublicWidget = loader ? lazy(loader) : null

export function PublicChatSlot(props: PublicWidgetProps) {
  if (!PublicWidget) return null
  return (
    <ErrorBoundary>
      <Suspense fallback={null}>
        <PublicWidget {...props} />
      </Suspense>
    </ErrorBoundary>
  )
}
