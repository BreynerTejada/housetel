import { CircleCheck, CircleX, Clock3, FileClock, Hourglass, Play, SlidersHorizontal, Workflow, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatRelative, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useAutomations, useRunAutomation, useUpdateAutomation, type Automation, type RunStatus } from '../api'
import { RecentRuns, RunStatusBadge } from '../components/badges'
import { ParamsDialog } from '../components/ParamsDialog'
import { RunHistorySheet } from '../components/RunHistorySheet'
import { RailLegend, ScheduleRail } from '../components/ScheduleRail'
import { dailyPattern, hotelClock, minutesNow } from '../lib/cron'
import { appLabel, localized } from '../lib/labels'

/** Modules in the order a hotel lives its day: the front desk first, platform plumbing last. */
const APP_ORDER = ['frontdesk', 'bookings', 'housekeeping', 'finance', 'messaging', 'distribution', 'compliance', 'revenue', 'ai']

function groupByApp(items: Automation[]): { app: string; items: Automation[] }[] {
  const groups = new Map<string, Automation[]>()
  for (const item of items) groups.set(item.app, [...(groups.get(item.app) ?? []), item])
  const rank = (app: string) => {
    const index = APP_ORDER.indexOf(app)
    return index === -1 ? APP_ORDER.length : index
  }
  return [...groups.entries()].sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b)).map(([app, list]) => ({ app, items: list }))
}

/** "Ejecutando…" stays at least this long, so an instant run still reads as "it ran" and not as a flicker. */
const MIN_RUNNING_MS = 700

/** What "Ejecutar ahora" answered, kept on the row until the next run or until it is dismissed. */
interface RunNotice {
  status: RunStatus | 'queued'
  summary: string
  at: string
}

/** The hotel's "now" (minutes after midnight), refreshed every minute for the marker on the rails. */
function useNowMinutes(timeZone: string | undefined): number {
  const [now, setNow] = useState(() => minutesNow(timeZone))
  useEffect(() => {
    const id = window.setInterval(() => setNow(minutesNow(timeZone)), 60_000)
    return () => window.clearInterval(id)
  }, [timeZone])
  return now
}

/** `/app/settings/automations`: what runs on its own, when (24-hour rail in hotel time), how it went, run now. */
export default function AutomationsPage() {
  const { t, i18n } = useTranslation('control')
  const { property } = useActiveProperty()
  const timeZone = property?.timezone
  const query = useAutomations()
  const nowMinutes = useNowMinutes(timeZone)
  const [paramsFor, setParamsFor] = useState<string | null>(null)
  const [historyFor, setHistoryFor] = useState<string | null>(null)
  const items = useMemo(() => query.data ?? [], [query.data])
  const groups = useMemo(() => groupByApp(items), [items])
  // The next *daily* job (night audit, room assignment, cleaning tasks…): the ones that run every few minutes
  // would always win and say nothing.
  const next = useMemo(
    () =>
      items
        .filter((item) => {
          if (!item.enabled || !item.next_run_at) return false
          const pattern = dailyPattern(item.schedule.cron, item.schedule.every_seconds)
          return pattern !== null && !pattern.continuous && pattern.times.length <= 6
        })
        .sort((a, b) => (a.next_run_at ?? '').localeCompare(b.next_run_at ?? ''))[0] ?? null,
    [items],
  )
  const paramsAutomation = items.find((item) => item.code === paramsFor) ?? null
  const historyAutomation = items.find((item) => item.code === historyFor) ?? null

  return (
    <div className="grid gap-6">
      <PageHeader
        title={t('automations.title')}
        description={t('automations.description')}
        className="pb-0"
        actions={
          next && (
            <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-[13px] text-muted shadow-xs">
              <Clock3 aria-hidden className="size-4 text-accent" />
              <span>
                {t('automations.nextUp', { name: localized(next.name, i18n.language), time: hotelClock(next.next_run_at, timeZone) })}
              </span>
            </p>
          )
        }
      />

      {query.isPending ? (
        <LoadingState variant="rows" rows={8} className="p-0" />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState icon={Workflow} title={t('automations.empty')} />
      ) : (
        <div className="grid gap-6">
          {groups.map((group) => (
            <section key={group.app} aria-labelledby={`automations-${group.app}`} className="grid gap-2">
              <h2 id={`automations-${group.app}`} className="eyebrow flex items-center gap-2 px-1">
                {appLabel(t, i18n, group.app)}
                <span className="num font-semibold text-subtle">{group.items.length}</span>
              </h2>
              <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-xs">
                {group.items.map((item) => (
                  <AutomationRow
                    key={item.code}
                    automation={item}
                    nowMinutes={nowMinutes}
                    timeZone={timeZone}
                    onParams={() => setParamsFor(item.code)}
                    onHistory={() => setHistoryFor(item.code)}
                  />
                ))}
              </div>
            </section>
          ))}
          <p className="px-1 text-xs text-subtle">{t('automations.rail.footnote', { zone: timeZone ?? 'America/Bogota' })}</p>
        </div>
      )}

      <ParamsDialog automation={paramsAutomation} open={paramsAutomation !== null} onOpenChange={(open) => !open && setParamsFor(null)} />
      <RunHistorySheet automation={historyAutomation} open={historyAutomation !== null} onOpenChange={(open) => !open && setHistoryFor(null)} />
    </div>
  )
}

function AutomationRow({
  automation,
  nowMinutes,
  timeZone,
  onParams,
  onHistory,
}: {
  automation: Automation
  nowMinutes: number
  timeZone: string | undefined
  onParams: () => void
  onHistory: () => void
}) {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('control.automations')
  const update = useUpdateAutomation()
  const run = useRunAutomation()
  const name = localized(automation.name, i18n.language)
  const schedule = localized(automation.schedule.text, i18n.language)
  const hasParams = Object.keys(automation.param_types).length > 0
  const someDays = dailyPattern(automation.schedule.cron, automation.schedule.every_seconds)?.someDays ?? false
  const last = automation.last_run
  const titleId = `automation-${automation.code.replace(/\W/g, '-')}`

  async function toggle(enabled: boolean) {
    try {
      await update.mutateAsync({ code: automation.code, body: { enabled } })
      toast.success(t(enabled ? 'automations.toasts.enabled' : 'automations.toasts.disabled', { name }))
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  const [notice, setNotice] = useState<RunNotice | null>(null)
  const [holding, setHolding] = useState(false)
  const running = run.isPending || holding

  async function runNow() {
    setNotice(null)
    setHolding(true)
    const minimum = new Promise((resolve) => window.setTimeout(resolve, MIN_RUNNING_MS))
    try {
      const [result] = await Promise.all([run.mutateAsync(automation.code), minimum])
      if (result.queued || !result.run) {
        setNotice({ status: 'queued', summary: t('automations.notice.queued'), at: new Date().toISOString() })
        toast.info(t('automations.toasts.queued', { name }), { duration: 8000 })
        return
      }
      const summary = result.run.summary || t(`runStatus.${result.run.status}`)
      setNotice({ status: result.run.status, summary, at: result.run.finished_at ?? result.run.started_at })
      if (result.run.status === 'failed') toast.error(t('automations.toasts.ranFailed', { name, summary }), { duration: 8000 })
      else toast.success(t('automations.toasts.ran', { name, summary }), { duration: 8000 })
    } catch (error) {
      await minimum
      toast.error(errorMessage(error, t))
    } finally {
      setHolding(false)
    }
  }

  return (
    <article aria-labelledby={titleId} className={cn('grid gap-x-6 gap-y-3 px-4 py-4 sm:px-5 md:grid-cols-[minmax(0,1fr)_15rem] xl:grid-cols-[minmax(0,1fr)_18rem]')}>
      <header className="flex min-w-0 items-start gap-3 md:col-start-1">
        <Switch
          checked={automation.enabled}
          onCheckedChange={(checked) => void toggle(checked)}
          disabled={!canManage || update.isPending}
          aria-label={t('automations.toggle', { name })}
          className="mt-0.5"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 id={titleId} className={cn('text-[15px] leading-5 font-bold', automation.enabled ? 'text-fg' : 'text-muted')}>
              {name}
            </h3>
            {!automation.enabled && <Badge tone="stone">{t('automations.paused')}</Badge>}
            {hasParams && JSON.stringify(automation.params) !== JSON.stringify(automation.default_params) && (
              <Badge tone="outline">{t('automations.customized')}</Badge>
            )}
          </div>
          <p className="mt-0.5 text-[13px] text-muted">{localized(automation.description, i18n.language)}</p>
        </div>
      </header>

      <div className="grid content-start gap-1 md:col-start-2 md:row-span-3 md:row-start-1 md:pt-0.5">
        <ScheduleRail
          cron={automation.schedule.cron}
          everySeconds={automation.schedule.every_seconds}
          label={t('automations.rail.label', { name, schedule })}
          nowMinutes={nowMinutes}
          paused={!automation.enabled}
        />
        <RailLegend />
        <p className="text-xs text-fg/85">
          {schedule}
          {someDays && <span className="text-muted"> · {t('automations.rail.someDays')}</span>}
        </p>
        {automation.enabled && automation.next_run_at && (
          <p className="num text-xs text-muted">{t('automations.nextAt', { time: hotelClock(automation.next_run_at, timeZone) })}</p>
        )}
      </div>

      <div className="grid min-w-0 gap-1.5 md:col-start-1 md:pl-12">
        {last ? (
          <>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
              <RunStatusBadge status={last.status} />
              <time dateTime={last.started_at} title={last.started_at}>
                {formatRelative(last.started_at, lang)}
              </time>
              <span aria-hidden>·</span>
              <span>{last.manual ? t('automations.manual') : t('automations.scheduled')}</span>
              {automation.stats_7d.failed > 0 && (
                <>
                  <span aria-hidden>·</span>
                  <span className="font-semibold text-danger-ink">{t('automations.failed7d', { count: automation.stats_7d.failed })}</span>
                </>
              )}
            </div>
            {last.summary && <p className="line-clamp-2 text-[13px] break-words text-fg/85">{last.summary}</p>}
          </>
        ) : (
          <p className="text-xs text-muted">{t('automations.neverRan')}</p>
        )}
        {automation.recent_runs.length > 1 && (
          <div className="flex items-center gap-2 text-2xs text-subtle">
            <RecentRuns runs={automation.recent_runs} />
            <span>{t('automations.runs7d', { count: automation.stats_7d.runs })}</span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 md:col-start-1 md:pl-12">
        <Button size="sm" onClick={() => void runNow()} loading={running} disabled={!canManage || running}>
          {!running && <Play aria-hidden />}
          {running ? t('automations.running') : t('automations.runNow')}
        </Button>
        <Button size="sm" variant="ghost" onClick={onHistory}>
          <FileClock aria-hidden />
          {t('automations.history')}
        </Button>
        {hasParams && canManage && (
          <Button size="sm" variant="ghost" onClick={onParams}>
            <SlidersHorizontal aria-hidden />
            {t('automations.params')}
          </Button>
        )}
      </div>
      <div role="status" aria-live="polite" className="empty:hidden md:col-start-1 md:pl-12">
        {notice && <RunResultNotice notice={notice} lang={lang} onDismiss={() => setNotice(null)} />}
      </div>
    </article>
  )
}

const NOTICE_STYLE: Record<RunNotice['status'], { box: string; icon: typeof CircleCheck }> = {
  success: { box: 'border-success/30 bg-success-soft text-success-ink', icon: CircleCheck },
  partial: { box: 'border-warning/30 bg-warning-soft text-warning-ink', icon: CircleCheck },
  skipped: { box: 'border-border bg-surface-2 text-fg', icon: CircleCheck },
  running: { box: 'border-info/30 bg-info-soft text-info-ink', icon: Hourglass },
  queued: { box: 'border-info/30 bg-info-soft text-info-ink', icon: Hourglass },
  failed: { box: 'border-danger/30 bg-danger-soft text-danger-ink', icon: CircleX },
}

/**
 * The answer of "Ejecutar ahora" next to the button that asked for it. It stays (until the next run or ×)
 * because a run that finishes in a few milliseconds would otherwise only flash a toast in a corner.
 */
function RunResultNotice({ notice, lang, onDismiss }: { notice: RunNotice; lang: 'es' | 'en'; onDismiss: () => void }) {
  const { t } = useTranslation('control')
  const style = NOTICE_STYLE[notice.status]
  const Icon = style.icon
  return (
    <div className={cn('flex items-start gap-2 rounded-lg border px-3 py-2 text-[13px] animate-pop-in', style.box)}>
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <p className="min-w-0 flex-1 break-words">
        <span className="font-semibold">
          {notice.status === 'queued' ? t('automations.notice.queuedTitle') : t('automations.notice.title', { status: t(`runStatus.${notice.status}`) })}
        </span>
        <span className="opacity-80"> · {formatRelative(notice.at, lang)}</span>
        <span className="block">{notice.summary}</span>
      </p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label={t('automations.notice.dismiss')}
        className="-mr-1 grid size-6 shrink-0 place-items-center rounded-md opacity-70 hover:opacity-100 focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:outline-none"
      >
        <X aria-hidden className="size-3.5" />
      </button>
    </div>
  )
}
