import { CircleOff, FileClock, Play, Scale, Settings2, SlidersHorizontal, Sparkles, Zap } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { useRevenueSummary, useRunNow } from '../api'
import { BoundsPanel } from '../components/BoundsPanel'
import { HistoryPanel } from '../components/HistoryPanel'
import { RecommendationsPanel } from '../components/RecommendationsPanel'
import { RulesPanel } from '../components/RulesPanel'
import { SettingsPanel } from '../components/SettingsPanel'

const TABS = ['recommendations', 'rules', 'bounds', 'history', 'settings'] as const
type Tab = (typeof TABS)[number]

/**
 * `/app/revenue`: price recommendations computed by the property's rules (heatmap, detail, mass approval),
 * the rules themselves, price bounds, run history and settings. It starts over when the property changes.
 */
export default function RevenuePage() {
  const { property } = useActiveProperty()
  if (!property) return <LoadingState variant="rows" rows={8} />
  return <Revenue key={property.id} today={property.business_date} />
}

function Revenue({ today }: { today: string }) {
  const { t } = useTranslation('revenue')
  const canManage = useCan('revenue.manage')
  const [params, setParams] = useSearchParams()
  const asked = params.get('tab')
  const tab: Tab = (TABS as readonly string[]).includes(asked ?? '') ? (asked as Tab) : 'recommendations'
  const summary = useRevenueSummary()
  const runNow = useRunNow()

  function openTab(next: string) {
    setParams(next === 'recommendations' ? {} : { tab: next }, { replace: true })
  }

  function run() {
    runNow.mutate(undefined, {
      onSuccess: (result) =>
        toast.success(
          result.auto_applied_count > 0
            ? t('run.doneAuto', { count: result.auto_applied_count })
            : t('run.done', { count: result.recommendations_count }),
        ),
      onError: (error) => toast.error(errorMessage(error, t)),
    })
  }

  return (
    <div className="grid gap-4">
      <PageHeader
        className="pb-2"
        title={t('page.title')}
        description={t('page.description')}
        actions={
          canManage && (
            <Button variant="primary" onClick={run} loading={runNow.isPending} disabled={summary.data?.enabled === false}>
              <Play aria-hidden />
              {t('run.button')}
            </Button>
          )
        }
      />

      {summary.data?.enabled === false && (
        <p className="flex flex-wrap items-center gap-2 rounded-lg border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-warning-ink">
          <CircleOff aria-hidden className="size-4 shrink-0" />
          <span className="flex-1">{t('page.disabled')}</span>
          {canManage && (
            <Link to="?tab=settings" replace className="font-semibold underline-offset-4 hover:underline">
              {t('page.openSettings')}
            </Link>
          )}
        </p>
      )}
      {summary.data?.enabled !== false && summary.data?.auto_apply && (
        <p className="flex items-center gap-2 rounded-lg border border-info/25 bg-info-soft px-4 py-3 text-sm text-info-ink">
          <Zap aria-hidden className="size-4 shrink-0" />
          {t('page.autoApplyOn')}
        </p>
      )}

      <Tabs value={tab} onValueChange={openTab}>
        <TabsList aria-label={t('page.sections')}>
          <TabsTrigger value="recommendations">
            <Sparkles aria-hidden />
            {t('tabs.recommendations')}
            {summary.data && summary.data.pending > 0 && (
              <span className="num rounded-full bg-accent-soft px-1.5 text-2xs leading-4 font-bold text-accent-ink">{summary.data.pending}</span>
            )}
          </TabsTrigger>
          <TabsTrigger value="rules">
            <SlidersHorizontal aria-hidden />
            {t('tabs.rules')}
          </TabsTrigger>
          <TabsTrigger value="bounds">
            <Scale aria-hidden />
            {t('tabs.bounds')}
          </TabsTrigger>
          <TabsTrigger value="history">
            <FileClock aria-hidden />
            {t('tabs.history')}
          </TabsTrigger>
          <TabsTrigger value="settings">
            <Settings2 aria-hidden />
            {t('tabs.settings')}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="recommendations">
          <RecommendationsPanel today={today} />
        </TabsContent>
        <TabsContent value="rules">
          <RulesPanel today={today} />
        </TabsContent>
        <TabsContent value="bounds">
          <BoundsPanel />
        </TabsContent>
        <TabsContent value="history">
          <HistoryPanel />
        </TabsContent>
        <TabsContent value="settings">
          <SettingsPanel />
        </TabsContent>
      </Tabs>
    </div>
  )
}
