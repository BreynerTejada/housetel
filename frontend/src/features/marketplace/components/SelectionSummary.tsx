import { X } from 'lucide-react'
import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { useChatOffset } from '@/features/ai/lib/chat-offset'
import { cn } from '@/lib/utils'
import type { Offer } from '../api'
import { selectionSummary, type SelectionItem } from '../lib/selection'
import { tr } from '../lib/text'

interface SelectionSummaryProps {
  items: SelectionItem[]
  offers: Offer[]
  currency: string
  taxExempt: boolean
  checkoutHref: string
  onRemove: (item: SelectionItem) => void
  className?: string
}

/** What the guest picked, the total and the way to the checkout (sticky on wide screens). */
export function SelectionSummary({ items, offers, currency, taxExempt, checkoutHref, onRemove, className }: SelectionSummaryProps) {
  const { t, i18n } = useTranslation('marketplace')
  const summary = selectionSummary(items, offers)
  const lines = items.flatMap((item) => {
    const offer = offers.find((candidate) => candidate.room_type_id === item.roomTypeId && candidate.rate_plan_id === item.ratePlanId)
    return offer ? [{ item, offer }] : []
  })

  return (
    <div className={cn('rounded-2xl border border-border bg-surface p-5 shadow-sm', className)}>
      <h2 className="text-base font-bold text-fg">{t('hotel.summary.title')}</h2>
      {lines.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t('hotel.summary.empty')}</p>
      ) : (
        <ul className="mt-3 divide-y divide-border">
          {lines.map(({ item, offer }) => {
            const room = tr(offer.room_type.name, i18n.language)
            const plan = tr(offer.rate_plan.name, i18n.language)
            return (
              <li key={`${item.roomTypeId}:${item.ratePlanId}`} className="flex items-start gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-fg">{t('hotel.summary.line', { quantity: item.quantity, room })}</p>
                  <p className="text-xs text-muted">{plan}</p>
                </div>
                <MoneyText value={Number(offer.total) * item.quantity} currency={currency} className="text-sm font-semibold" />
                <button
                  type="button"
                  onClick={() => onRemove(item)}
                  aria-label={t('hotel.summary.remove', { room, plan })}
                  className="-mr-1 rounded-md p-0.5 text-subtle transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                >
                  <X aria-hidden className="size-4" />
                </button>
              </li>
            )
          })}
        </ul>
      )}
      <div className="mt-3 flex items-baseline justify-between gap-3 border-t border-border pt-3">
        <span className="text-sm font-semibold text-fg">{t('hotel.summary.total')}</span>
        <span className="text-right">
          <MoneyText value={summary.total} currency={currency} className="block text-2xl font-extrabold tracking-[-0.02em]" />
          <span className="text-xs text-muted">{taxExempt ? t('hotel.summary.taxExempt') : t('hotel.summary.taxes')}</span>
        </span>
      </div>
      {lines.length > 0 ? (
        <Button asChild variant="primary" size="lg" className="mt-4 w-full">
          <Link to={checkoutHref}>{t('hotel.summary.book')}</Link>
        </Button>
      ) : (
        <Button variant="primary" size="lg" className="mt-4 w-full" disabled>
          {t('hotel.summary.book')}
        </Button>
      )}
      <p className="mt-2 text-center text-xs text-muted">{t('hotel.summary.noCharge')}</p>
    </div>
  )
}

/**
 * Phones: the total and the button stay at the bottom of the screen once something is picked. The hotel's chat
 * bubble floats above the bar (it reads the bar's height), so it never covers "Reservar" (plan P6).
 */
export function MobileSelectionBar({ items, offers, currency, checkoutHref }: Omit<SelectionSummaryProps, 'onRemove' | 'taxExempt'>) {
  const { t } = useTranslation('marketplace')
  const summary = selectionSummary(items, offers)
  const bar = useRef<HTMLDivElement>(null)
  useChatOffset(bar, summary.lines > 0)
  if (summary.lines === 0) return null
  return (
    <div
      ref={bar}
      className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface/95 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-lg backdrop-blur lg:hidden"
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
        <div>
          <p className="text-xs text-muted">{t('hotel.summary.rooms', { count: summary.rooms })}</p>
          <MoneyText value={summary.total} currency={currency} className="text-lg font-extrabold" />
        </div>
        <Button asChild variant="primary" size="lg">
          <Link to={checkoutHref}>{t('hotel.summary.book')}</Link>
        </Button>
      </div>
    </div>
  )
}
