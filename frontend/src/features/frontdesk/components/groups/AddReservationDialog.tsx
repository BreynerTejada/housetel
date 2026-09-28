import { Search, UsersRound } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { LoadingState } from '@/components/LoadingState'
import { StatusBadge } from '@/components/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useDebouncedValue } from '@/features/guests/hooks'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { updateReservation, useRefreshFrontDesk, useReservations, type ReservationListItem } from '../../api'

/**
 * Bring a reservation that already exists into the group (pilot P3): search it by code, guest, email or phone
 * and add it. One in another group moves here (the backend refuses when it holds rooms of that group's
 * allotment).
 */
export function AddReservationDialog({
  open,
  onOpenChange,
  groupId,
  groupName,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  groupId: string
  groupName: string
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const searchId = useId()
  const refresh = useRefreshFrontDesk()
  const [text, setText] = useState('')
  const q = useDebouncedValue(text, 300).trim()
  const params = useMemo(
    () => ({ q, status: ['tentative', 'confirmed', 'checked_in'], page_size: 8, ordering: 'checkin_date' }),
    [q],
  )
  const results = useReservations(params)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const items = (results.data?.results ?? []).filter((item) => item.group?.id !== groupId)

  async function add(reservation: ReservationListItem) {
    setBusy(reservation.id)
    setError(null)
    try {
      await updateReservation(reservation.id, { group_id: groupId })
      await refresh()
      toast.success(t('groups.addExisting.done', { code: reservation.code, name: groupName }))
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err, t))
    } finally {
      setBusy(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{t('groups.addExisting.title')}</DialogTitle>
          <DialogDescription>{t('groups.addExisting.description', { name: groupName })}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <label htmlFor={searchId} className="relative block">
            <span className="sr-only">{t('groups.addExisting.search')}</span>
            <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
            <Input
              id={searchId}
              type="search"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder={t('groups.addExisting.search')}
              className="pl-9"
              autoComplete="off"
            />
          </label>
          <div className="max-h-80 overflow-y-auto" aria-live="polite">
            {results.isPending ? (
              <LoadingState variant="rows" rows={3} className="p-0" />
            ) : items.length === 0 ? (
              <p className="px-1 py-6 text-center text-[13px] text-muted">{q ? t('groups.addExisting.none') : t('groups.addExisting.hint')}</p>
            ) : (
              <ul className="grid gap-1.5">
                {items.map((item) => (
                  <li key={item.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border px-3 py-2">
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="num text-[13px] font-bold text-fg">{item.code}</span>
                        <StatusBadge kind="reservation" status={item.status} />
                        {item.group && (
                          <Badge tone="info" className="max-w-44">
                            <UsersRound aria-hidden />
                            <span className="truncate">{item.group.name}</span>
                          </Badge>
                        )}
                      </span>
                      <span className="block truncate text-[13px] text-fg">{item.booker.full_name}</span>
                      <span className="num block text-xs text-muted">
                        {formatDateRange(item.checkin_date, item.checkout_date, lang)} · {t('groups.rooms', { count: item.stays.length })}
                      </span>
                    </span>
                    <Button size="sm" variant={item.group ? 'secondary' : 'primary'} loading={busy === item.id} disabled={Boolean(busy)} onClick={() => void add(item)}>
                      {item.group ? t('groups.addExisting.move') : t('groups.addExisting.add')}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
