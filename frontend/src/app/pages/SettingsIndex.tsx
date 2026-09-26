import { ChevronRight, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { useNav } from '@/app/extensions'
import { EmptyState } from '@/components/EmptyState'
import { PageHeader } from '@/components/PageHeader'

/** `/app/settings`: every settings section the user can open, with what it is for. */
export function SettingsIndex() {
  const { t } = useTranslation()
  const items = useNav('settings')
  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader title={t('settings.title')} description={t('settings.description')} />
      {items.length === 0 ? (
        <EmptyState icon={Settings} title={t('settings.empty')} />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => {
            const Icon = item.icon
            return (
              <li key={item.id}>
                <Link
                  to={item.path}
                  className="group flex h-full items-start gap-3 rounded-lg border border-border bg-surface p-4 shadow-xs transition-colors hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                >
                  <span className="grid size-9 shrink-0 place-items-center rounded-md bg-surface-2 text-muted transition-colors group-hover:bg-accent-soft group-hover:text-accent-ink">
                    <Icon aria-hidden className="size-[18px]" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold text-fg">{t(item.labelKey)}</span>
                    {item.descriptionKey && <span className="mt-0.5 block text-[13px] text-muted">{t(item.descriptionKey)}</span>}
                  </span>
                  <ChevronRight aria-hidden className="mt-0.5 size-4 shrink-0 text-subtle transition-transform group-hover:translate-x-0.5" />
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
