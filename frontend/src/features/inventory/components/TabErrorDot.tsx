import { useTranslation } from 'react-i18next'

/** Marks a tab that holds fields with errors (a dot, and ", con errores" in its accessible name). */
export function TabErrorDot() {
  const { t } = useTranslation('inventory')
  return (
    <>
      <span aria-hidden className="size-1.5 rounded-full bg-danger" />
      <span className="sr-only">{t('common.hasErrors')}</span>
    </>
  )
}
