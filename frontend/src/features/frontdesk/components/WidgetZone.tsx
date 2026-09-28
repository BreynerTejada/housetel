import { Suspense, useId } from 'react'
import { useTranslation } from 'react-i18next'
import type { DashboardWidget } from '@/app/extensions'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

/** Columns a widget takes on the 6-column (tablet) and 12-column (desktop) grids. */
const SPAN: Record<DashboardWidget['size'], string> = {
  sm: 'md:col-span-3 xl:col-span-3',
  md: 'md:col-span-6 xl:col-span-6',
  lg: 'md:col-span-6 xl:col-span-8',
  full: 'md:col-span-6 xl:col-span-12',
}

/**
 * The Today panel's widget zone (plan §E `widgets.tsx`): cleaning progress, alerts, price recommendations…
 * from other features, already filtered by permission and sorted by `useWidgets()`. Each widget draws its own
 * card; one that fails is replaced by a quiet note and never takes the panel down.
 */
export function WidgetZone({ widgets }: { widgets: DashboardWidget[] }) {
  const { t } = useTranslation('frontdesk')
  const titleId = useId()
  if (widgets.length === 0) return null
  return (
    <section aria-labelledby={titleId} className="grid gap-3">
      <h2 id={titleId} className="eyebrow">
        {t('widgets.title')}
      </h2>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-6 xl:grid-cols-12">
        {widgets.map(({ id, size, Component }) => (
          <div key={id} data-widget={id} className={cn('min-w-0', SPAN[size])}>
            <ErrorBoundary
              fallback={
                <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-[13px] text-muted">
                  {t('widgets.failed')}
                </p>
              }
            >
              <Suspense fallback={<Skeleton className="h-32 rounded-xl" />}>
                <Component />
              </Suspense>
            </ErrorBoundary>
          </div>
        ))}
      </div>
    </section>
  )
}
