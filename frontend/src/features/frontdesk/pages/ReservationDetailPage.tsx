import { useQueryClient } from '@tanstack/react-query'
import { Ban, BedDouble, ChevronRight, CircleCheck, LogIn, LogOut, MoreHorizontal, Plus, SearchX, Star, UserX, UsersRound } from 'lucide-react'
import { Suspense, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { useReservationActions, useReservationTabs, type ReservationAction } from '@/app/extensions'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { StatusBadge } from '@/components/StatusBadge'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useActiveProperty } from '@/lib/auth'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { bookingKeys, confirmReservation, markNoShow, useRefreshFrontDesk, useReservation, type ReservationDetail, type StayDetail } from '../api'
import { AddStayDialog } from '../components/AddStayDialog'
import { AssignRoomDialog } from '../components/AssignRoomDialog'
import { CancelReservationDialog } from '../components/CancelReservationDialog'
import { CancelStayDialog } from '../components/CancelStayDialog'
import { CheckInDialog } from '../components/CheckInDialog'
import { CheckOutDialog } from '../components/CheckOutDialog'
import { GuestsPanel } from '../components/GuestsPanel'
import { ModifyStayDialog } from '../components/ModifyStayDialog'
import { ReservationFacts } from '../components/ReservationFacts'
import { StayCard } from '../components/StayCard'
import { stayLine } from '../lib/labels'
import { activeStays, stayActions, type StayAction } from '../lib/stays'

type OpenDialog =
  | { kind: StayAction; stay: StayDetail }
  | { kind: 'cancelReservation' }
  | { kind: 'addStay' }
  | { kind: 'noShow' }
  | { kind: 'extension'; action: ReservationAction }

const BUILT_IN_TABS = ['summary', 'guests'] as const

/**
 * `/app/reservations/:id` (plan C1): who, when, where and how much; the stays with their room actions
 * (assign or move, change dates with the new price, check-in/out); tabs Summary and Guests plus the ones other
 * features register (`useReservationTabs()`: folio, online check-in, messages, legal, history); and the actions
 * menu — confirm, no-show, cancel with its penalty — plus `useReservationActions()`.
 */
export default function ReservationDetailPage() {
  const { t } = useTranslation('frontdesk')
  const { id = '' } = useParams()
  const reservation = useReservation(id)

  if (reservation.isError) {
    if (isApiError(reservation.error) && reservation.error.status === 404) {
      return (
        <EmptyState
          icon={SearchX}
          title={t('detail.notFound')}
          description={t('detail.notFoundHint')}
          action={
            <Button asChild>
              <Link to="/app/reservations">{t('detail.backToList')}</Link>
            </Button>
          }
        />
      )
    }
    return <ErrorState error={reservation.error} onRetry={() => reservation.refetch()} />
  }
  if (!reservation.data) return <LoadingState />
  return <Detail reservation={reservation.data} />
}

function Detail({ reservation }: { reservation: ReservationDetail }) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const bd = property?.business_date ?? reservation.checkin_date
  const [searchParams, setSearchParams] = useSearchParams()
  const extensionTabs = useReservationTabs()
  const extensionActions = useReservationActions()
  const canCheck = useCan('bookings.checkin')
  const canManage = useCan('bookings.manage')
  const canCancel = useCan('bookings.cancel')
  const queryClient = useQueryClient()
  const refresh = useRefreshFrontDesk()
  const [dialog, setDialog] = useState<OpenDialog | null>(null)
  const close = () => setDialog(null)

  const tabIds = [...BUILT_IN_TABS, ...extensionTabs.map((tab) => tab.id)]
  const requestedTab = searchParams.get('tab')
  const tab = requestedTab && tabIds.includes(requestedTab) ? requestedTab : 'summary'
  const liveStays = reservation.stays.filter((stay) => stay.status !== 'cancelled' && stay.status !== 'no_show')
  const single = liveStays.length === 1 ? liveStays[0] : undefined
  const canAddRoom = canManage && ['tentative', 'confirmed', 'checked_in'].includes(reservation.status)
  const roomsCount = activeStays(reservation).length
  const headerAction = single && canCheck ? stayActions(single, bd).find((action) => action === 'checkin' || action === 'checkout') : undefined
  const pending = reservation.status === 'tentative' || reservation.status === 'confirmed'
  const canNoShow = reservation.status === 'confirmed' && reservation.checkin_date < bd
  const balance = Number(reservation.balance)
  const guestLine = stayLine(t, lang, {
    checkin: reservation.checkin_date,
    checkout: reservation.checkout_date,
    nights: reservation.nights,
    adults: reservation.adults,
    children: reservation.children,
  })

  async function quick(action: () => Promise<ReservationDetail>, message: string) {
    try {
      const detail = await action()
      queryClient.setQueryData(bookingKeys.reservation(reservation.id), detail)
      await refresh()
      toast.success(message)
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  const chips: { key: string; tone: BadgeTone; text: string }[] = []
  if (reservation.flags.ready_for_checkin) chips.push({ key: 'ready', tone: 'success', text: t('detail.flags.ready') })
  else if (reservation.flags.arrives_today) chips.push({ key: 'arrives', tone: 'info', text: t('detail.flags.arrivesToday') })
  if (reservation.flags.departs_today) chips.push({ key: 'departs', tone: 'info', text: t('detail.flags.departsToday') })
  if (reservation.flags.unassigned) chips.push({ key: 'unassigned', tone: 'warning', text: t('detail.flags.unassigned') })
  if (reservation.status === 'tentative') chips.push({ key: 'hold', tone: 'warning', text: t('detail.flags.tentative') })

  const hasMenu = (pending && (canManage || canCancel)) || extensionActions.length > 0

  return (
    <div className="mx-auto grid max-w-6xl grid-cols-1 gap-6">
      <nav aria-label={t('detail.breadcrumb')} className="flex items-center gap-1 text-[13px] text-muted">
        <Link to="/app/reservations" className="rounded-sm hover:text-fg hover:underline">
          {t('nav.reservations')}
        </Link>
        <ChevronRight aria-hidden className="size-3.5 text-subtle" />
        <span className="num">{reservation.code}</span>
      </nav>

      <section aria-label={t('detail.region', { code: reservation.code })} className="rounded-xl border border-border bg-surface p-5 shadow-xs sm:p-6">
        <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="num text-[13px] font-bold tracking-wide text-muted">{reservation.code}</span>
              <StatusBadge kind="reservation" status={reservation.status} />
              <Badge tone="neutral">{reservation.channel_code || t(`sources.${reservation.source}`)}</Badge>
              {reservation.group && (
                <Link to={`/app/groups/${reservation.group.id}`} className="rounded-full focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:outline-none">
                  <Badge tone="info" className="hover:underline">
                    <UsersRound aria-hidden />
                    {t('detail.group', { name: reservation.group.name })}
                  </Badge>
                </Link>
              )}
            </div>
            <h1 className="mt-2 flex items-center gap-2 text-[26px] leading-8 tracking-[-0.025em] text-fg">
              {reservation.booker.full_name}
              {reservation.booker.is_vip && <Star role="img" aria-label={t('vip')} className="size-5 fill-warning text-warning" />}
            </h1>
            <p className="num mt-1 text-muted">{guestLine}</p>
            {chips.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {chips.map((chip) => (
                  <Badge key={chip.key} tone={chip.tone}>
                    {chip.text}
                  </Badge>
                ))}
              </div>
            )}
          </div>
          <div className="flex shrink-0 flex-col gap-3 md:items-end">
            <div className="md:text-right">
              <p className="text-[13px] font-semibold text-muted">{t('detail.balance')}</p>
              <MoneyText value={reservation.balance} currency={reservation.currency} className="block text-[26px] leading-8 font-semibold text-fg" />
              <p className={balance > 0 ? 'text-[13px] font-semibold text-warning-ink' : 'text-[13px] text-success-ink'}>
                {balance > 0 ? t('detail.due') : balance < 0 ? t('detail.inFavor') : t('detail.settled')}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {headerAction === 'checkin' && single && (
                <Button variant="primary" onClick={() => setDialog({ kind: 'checkin', stay: single })}>
                  <LogIn aria-hidden />
                  {t('actions.checkIn')}
                </Button>
              )}
              {headerAction === 'checkout' && single && (
                <Button variant="primary" onClick={() => setDialog({ kind: 'checkout', stay: single })}>
                  <LogOut aria-hidden />
                  {t('actions.checkOut')}
                </Button>
              )}
              {hasMenu && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button>
                      <MoreHorizontal aria-hidden />
                      {t('detail.moreActions')}
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {reservation.status === 'tentative' && canManage && (
                      <DropdownMenuItem onSelect={() => void quick(() => confirmReservation(reservation.id), t('detail.confirmed'))}>
                        <CircleCheck aria-hidden />
                        {t('detail.confirm')}
                      </DropdownMenuItem>
                    )}
                    {canNoShow && canManage && (
                      <DropdownMenuItem onSelect={() => setDialog({ kind: 'noShow' })}>
                        <UserX aria-hidden />
                        {t('detail.noShow')}
                      </DropdownMenuItem>
                    )}
                    {pending && canCancel && (
                      <DropdownMenuItem destructive onSelect={() => setDialog({ kind: 'cancelReservation' })}>
                        <Ban aria-hidden />
                        {t('cancel.confirm')}
                      </DropdownMenuItem>
                    )}
                    {extensionActions.length > 0 && pending && (canManage || canCancel) && <DropdownMenuSeparator />}
                    {extensionActions.map((action) => {
                      const Icon = action.icon
                      return (
                        <DropdownMenuItem key={action.id} destructive={action.danger} onSelect={() => setDialog({ kind: 'extension', action })}>
                          <Icon aria-hidden />
                          {t(action.labelKey)}
                        </DropdownMenuItem>
                      )
                    })}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          </div>
        </div>
      </section>

      <Tabs
        className="min-w-0"
        value={tab}
        onValueChange={(value) => setSearchParams(value === 'summary' ? {} : { tab: value }, { replace: true })}
      >
        <TabsList aria-label={t('detail.sections')}>
          <TabsTrigger value="summary">{t('tabs.summary')}</TabsTrigger>
          <TabsTrigger value="guests">{t('tabs.guests')}</TabsTrigger>
          {extensionTabs.map((extension) => (
            <TabsTrigger key={extension.id} value={extension.id}>
              {t(extension.labelKey)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="summary" className="grid grid-cols-1 gap-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 text-[15px] font-bold">
              <BedDouble aria-hidden className="size-4 text-muted" />
              {t('detail.rooms', { count: roomsCount })}
            </h2>
            {canAddRoom && (
              <Button size="sm" onClick={() => setDialog({ kind: 'addStay' })}>
                <Plus aria-hidden />
                {t('addStay.title')}
              </Button>
            )}
          </div>
          {reservation.stays.map((stay) => (
            <StayCard key={stay.id} reservation={reservation} stay={stay} onAction={(item, kind) => setDialog({ kind, stay: item })} />
          ))}
          <ReservationFacts reservation={reservation} />
        </TabsContent>
        <TabsContent value="guests">
          <GuestsPanel reservation={reservation} />
        </TabsContent>
        {extensionTabs.map(({ id, Component }) => (
          <TabsContent key={id} value={id}>
            <ErrorBoundary fallback={<ErrorState title={t('detail.tabFailed')} />}>
              <Suspense fallback={<LoadingState variant="rows" rows={4} />}>
                <Component reservationId={reservation.id} />
              </Suspense>
            </ErrorBoundary>
          </TabsContent>
        ))}
      </Tabs>

      {dialog?.kind === 'checkin' && <CheckInDialog open onOpenChange={(open) => !open && close()} stayId={dialog.stay.id} reservationId={reservation.id} />}
      {dialog?.kind === 'checkout' && <CheckOutDialog open onOpenChange={(open) => !open && close()} stayId={dialog.stay.id} reservationId={reservation.id} />}
      {dialog?.kind === 'assign' && <AssignRoomDialog open onOpenChange={(open) => !open && close()} reservation={reservation} stay={dialog.stay} />}
      {dialog?.kind === 'modify' && <ModifyStayDialog open onOpenChange={(open) => !open && close()} reservation={reservation} stay={dialog.stay} />}
      {dialog?.kind === 'cancelReservation' && <CancelReservationDialog open onOpenChange={(open) => !open && close()} reservation={reservation} />}
      {dialog?.kind === 'cancel' && <CancelStayDialog open onOpenChange={(open) => !open && close()} reservation={reservation} stay={dialog.stay} />}
      {dialog?.kind === 'addStay' && <AddStayDialog open onOpenChange={(open) => !open && close()} reservation={reservation} />}
      {dialog?.kind === 'noShow' && (
        <ConfirmDialog
          open
          onOpenChange={(open) => !open && close()}
          title={t('detail.noShowTitle', { code: reservation.code })}
          description={t('detail.noShowHint')}
          confirmLabel={t('detail.noShow')}
          onConfirm={() => quick(() => markNoShow(reservation.id), t('detail.noShowDone'))}
        />
      )}
      {dialog?.kind === 'extension' && (
        <Dialog open onOpenChange={(open) => !open && close()}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>{t(dialog.action.labelKey)}</DialogTitle>
              <DialogDescription className="sr-only">{reservation.code}</DialogDescription>
            </DialogHeader>
            <ErrorBoundary fallback={<ErrorState title={t('detail.actionFailed')} />}>
              <Suspense fallback={<LoadingState variant="rows" rows={2} />}>
                <dialog.action.Component reservationId={reservation.id} close={close} />
              </Suspense>
            </ErrorBoundary>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
