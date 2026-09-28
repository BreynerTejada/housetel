import { CircleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/** A step's validation message (an i18n key of the `frontdesk` namespace), announced when it appears. */
export function FieldError({ error, id }: { error?: string; id?: string }) {
  const { t } = useTranslation('frontdesk')
  if (!error) return null
  return (
    <p id={id} role="alert" className="flex items-center gap-1.5 text-[13px] font-semibold text-danger-ink">
      <CircleAlert aria-hidden className="size-3.5 shrink-0" />
      {t(error)}
    </p>
  )
}
