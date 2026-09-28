import { useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { calendarKeys, runStep, type CalendarData, type CalStay, type ReservationDetail } from '../api'
import { applyPlacement, undoSteps, type ChangePlan, type PlanContext, type PlanOption } from '../lib/dnd'
import { pick, placeLabel, type RoomIndex } from '../lib/labels'
import { calendarToast } from '../lib/toast'

interface Outcome {
  ok: boolean
  /** Steps the server accepted before a failure (a partial change cannot be rolled back locally). */
  done: number
  detail: ReservationDetail | null
  error?: unknown
}

/**
 * Runs a planned change of a stay against the bookings API. The grid moves the bar at once (optimistic
 * update of the visible range); a refusal before anything changed puts it back (rollback) and says why; a
 * refusal halfway says only part of the change happened. Whatever happens, the grid refetches the truth.
 * A room move at the same price and dates can be undone from its toast.
 */
export function useCalendarChanges({ queryKey, ctx, index }: { queryKey: QueryKey; ctx: PlanContext; index: RoomIndex }) {
  const queryClient = useQueryClient()
  const { t, i18n } = useTranslation('calendar')
  const lang = normalizeLang(i18n.language)

  const execute = useCallback(
    async (stay: CalStay, option: PlanOption): Promise<Outcome> => {
      await queryClient.cancelQueries({ queryKey: calendarKeys.calendar })
      const snapshot = queryClient.getQueryData<CalendarData>(queryKey)
      if (snapshot) queryClient.setQueryData<CalendarData>(queryKey, applyPlacement(snapshot, stay.id, option.next))
      let done = 0
      let detail: ReservationDetail | null = null
      try {
        for (const step of option.steps) {
          detail = await runStep(stay.id, step)
          done += 1
        }
        if (detail) queryClient.setQueryData(calendarKeys.reservation(detail.id), detail)
        return { ok: true, done, detail }
      } catch (error) {
        if (done === 0 && snapshot) queryClient.setQueryData<CalendarData>(queryKey, snapshot)
        return { ok: false, done, detail, error }
      } finally {
        void queryClient.invalidateQueries({ queryKey: calendarKeys.all })
      }
    },
    [queryClient, queryKey],
  )

  const reportFailure = useCallback(
    (outcome: Outcome) =>
      calendarToast.error(t(outcome.done === 0 ? 'toast.failed' : 'toast.partial', { detail: errorMessage(outcome.error, t) })),
    [t],
  )

  const undoAction = useCallback(
    (stay: CalStay, plan: ChangePlan, option: PlanOption) => {
      const steps = option === plan.primary ? undoSteps(plan, ctx) : null
      if (!steps) return undefined
      return {
        action: {
          label: t('toast.undo'),
          onClick: () => {
            void execute(stay, { steps, next: plan.from }).then((outcome) =>
              outcome.ok ? calendarToast.success(t('toast.undone')) : reportFailure(outcome),
            )
          },
        },
      }
    },
    [ctx, execute, reportFailure, t],
  )

  return useCallback(
    async (stay: CalStay, plan: ChangePlan, option: PlanOption) => {
      const outcome = await execute(stay, option)
      if (!outcome.ok) {
        reportFailure(outcome)
        return
      }
      const guest = stay.guest_name
      const next = option.next
      const from = plan.from
      const now = outcome.detail?.stays.find((candidate) => candidate.id === stay.id)
      const datesChanged = next.checkin !== from.checkin || next.checkout !== from.checkout

      if (plan.confirm === 'category' && option === plan.primary) {
        calendarToast.success(t('toast.categoryChanged', { guest, category: pick(index.roomTypeNames.get(next.roomTypeId), lang) }))
        return
      }
      if (datesChanged) {
        if (next.roomId && now && !now.room) {
          calendarToast.warning(t('toast.roomLost', { guest, room: index.rooms.get(next.roomId)?.number ?? '' }))
        } else {
          calendarToast.success(t('toast.datesChanged', { guest, range: formatDateRange(next.checkin, next.checkout, lang) }))
        }
        return
      }
      if (next.roomId === null) {
        calendarToast.success(t('toast.unassigned', { guest }), undoAction(stay, plan, option))
        return
      }
      const place = now?.bed
        ? t('bar.bed', { label: now.bed.label, room: now.room?.number ?? '' })
        : now?.room
          ? t('bar.room', { number: now.room.number })
          : placeLabel(t, index, next.roomId, next.bedId)
      calendarToast.success(t('toast.moved', { guest, place }), undoAction(stay, plan, option))
    },
    [execute, reportFailure, undoAction, t, lang, index],
  )
}
