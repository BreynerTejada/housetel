import { LinkIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { PortalFrame } from './PortalFrame'

/** A tampered, foreign or expired magic link: say it plainly and what to do (ask the hotel for a new one). */
export function InvalidLink() {
  const { t } = useTranslation('guestportal')
  return (
    <PortalFrame className="items-center justify-center px-4 py-16">
      <div className="grid max-w-sm justify-items-center gap-3 text-center">
        <span className="grid size-12 place-items-center rounded-2xl border border-border bg-surface-2 text-muted">
          <LinkIcon aria-hidden className="size-5" />
        </span>
        <h1 className="text-xl font-bold">{t('invalid.title')}</h1>
        <p className="text-sm text-muted">{t('invalid.text')}</p>
      </div>
    </PortalFrame>
  )
}
