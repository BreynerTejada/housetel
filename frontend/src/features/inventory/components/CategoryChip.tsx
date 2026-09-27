import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { I18nText } from '../api'
import { tr } from '../lib/text'

/** A category's color swatch (like the colored tag on a key), code and name. */
export function CategoryChip({
  code,
  name,
  color,
  className,
  showName = true,
}: {
  code: string
  name?: I18nText
  color: string
  className?: string
  showName?: boolean
}) {
  const { i18n } = useTranslation()
  return (
    <span className={cn('inline-flex min-w-0 items-center gap-2', className)}>
      <span aria-hidden className="size-3 shrink-0 rounded-[4px] ring-1 ring-black/5" style={{ backgroundColor: color }} />
      <span className="num text-[11px] font-bold tracking-wide text-muted">{code}</span>
      {showName && name && <span className="truncate font-semibold text-fg">{tr(name, i18n.language)}</span>}
    </span>
  )
}
