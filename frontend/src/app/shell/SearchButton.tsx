import { Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.userAgent)

export function SearchButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation()
  return (
    <>
      <button
        type="button"
        onClick={onClick}
        className="hidden h-8 w-56 items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-[13px] text-subtle shadow-xs transition-colors hover:border-border-strong hover:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 md:inline-flex"
      >
        <Search aria-hidden className="size-4" />
        <span>{t('topbar.search')}</span>
        <kbd className="ml-auto rounded border border-border bg-surface-2 px-1.5 font-sans text-[11px] font-semibold text-muted">
          {isMac ? '⌘K' : 'Ctrl K'}
        </kbd>
      </button>
      <Button variant="ghost" size="icon" className="md:hidden" onClick={onClick} aria-label={t('topbar.search')}>
        <Search aria-hidden />
      </Button>
    </>
  )
}
