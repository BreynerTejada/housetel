import { Star } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

/** Official star rating of the hotel (RNT), in ink: a fact about the place, not a status. */
export function Stars({ count, className }: { count: number | null | undefined; className?: string }) {
  const { t } = useTranslation('marketplace')
  if (!count) return null
  return (
    <span role="img" aria-label={t('stars', { count })} className={cn('inline-flex items-center gap-px text-fg', className)}>
      {Array.from({ length: count }, (_, index) => (
        <Star key={index} aria-hidden className="size-3 fill-current" strokeWidth={0} />
      ))}
    </span>
  )
}
