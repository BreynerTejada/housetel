import { useTranslation } from 'react-i18next'

/** Door hanger, the hotel way of saying "this room is being prepared". */
function DoorHanger() {
  return (
    <svg viewBox="0 0 72 112" className="h-24 w-auto" aria-hidden>
      <rect x="6" y="4" width="60" height="104" rx="12" className="fill-surface stroke-border" strokeWidth="1.5" />
      <circle cx="36" cy="26" r="11" className="fill-bg stroke-border" strokeWidth="1.5" />
      <path d="M36 37v5" className="stroke-border" strokeWidth="1.5" />
      <rect x="18" y="56" width="36" height="6" rx="3" className="fill-warning-soft" />
      <rect x="18" y="68" width="26" height="4" rx="2" className="fill-surface-3" />
      <rect x="18" y="78" width="30" height="4" rx="2" className="fill-surface-3" />
      <circle cx="54" cy="92" r="4" className="fill-warning" />
    </svg>
  )
}

/** Placeholder page used by feature stubs until their owner builds the real screen. */
export function UnderConstruction({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation()
  return (
    <section className="mx-auto flex max-w-md flex-col items-center px-6 py-16 text-center sm:py-24">
      <DoorHanger />
      <p className="eyebrow mt-8">{t('underConstruction.eyebrow')}</p>
      <h1 className="mt-2 text-2xl text-fg">{t(titleKey)}</h1>
      <p className="mt-3 text-muted">{t('underConstruction.description')}</p>
    </section>
  )
}

export default UnderConstruction
