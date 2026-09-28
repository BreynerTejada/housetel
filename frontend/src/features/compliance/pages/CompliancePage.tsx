import { Settings2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useActiveProperty } from '@/lib/auth'
import { useCan } from '@/lib/permissions'
import {
  useComplianceSettings,
  useInvoiceTotals,
  usePending,
  useSireReports,
  useTraRegistrations,
  type TraStatus,
} from '../api'
import { InvoiceSheet } from '../components/InvoiceSheet'
import { InvoicesTab } from '../components/InvoicesTab'
import { ObligationsBoard, type ComplianceTab } from '../components/ObligationsBoard'
import { PendingTab } from '../components/PendingTab'
import { SireTab } from '../components/SireTab'
import { TraTab } from '../components/TraTab'

const TABS: ComplianceTab[] = ['invoices', 'sire', 'tra', 'pending']

/** `/app/compliance`: DIAN electronic invoices, SIRE files for Migración Colombia and TRA registrations. */
export default function CompliancePage() {
  const { t } = useTranslation('compliance')
  const { property } = useActiveProperty()
  const canConfigure = useCan('compliance.settings')
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab') as ComplianceTab | null
  const tab: ComplianceTab = requested && TABS.includes(requested) ? requested : 'invoices'
  const invoiceId = params.get('invoice')
  const reportId = params.get('report')
  const traStatus = params.get('status') as TraStatus | null

  const pending = usePending()
  const totals = useInvoiceTotals()
  const reports = useSireReports()
  const registered = useTraRegistrations({ status: 'registered', page_size: 1 })
  const settings = useComplianceSettings()

  const update = (changes: Record<string, string | null>) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        for (const [key, value] of Object.entries(changes)) {
          if (value === null) next.delete(key)
          else next.set(key, value)
        }
        return next
      },
      { replace: true },
    )
  const openTab = (value: ComplianceTab) => update({ tab: value === 'invoices' ? null : value, report: null, status: null })
  const openInvoice = (id: string | null) => update({ invoice: id })
  const openReport = (id: string | null) => update(id ? { tab: 'sire', report: id } : { report: null })
  const sireMode = settings.data?.integrations.sire.mode ?? 'simulated'
  const pendingCount = pending.data?.counts.total ?? 0

  return (
    <div className="grid grid-cols-1 gap-6">
      <PageHeader
        title={t('page.title')}
        description={t('page.description')}
        className="pb-0"
        actions={
          canConfigure && (
            <Button asChild>
              <Link to="/app/settings/compliance">
                <Settings2 aria-hidden />
                {t('page.settings')}
              </Link>
            </Button>
          )
        }
      />

      {pending.isError ? (
        <ErrorState error={pending.error} onRetry={() => void pending.refetch()} />
      ) : (
        <ObligationsBoard
          businessDate={property?.business_date}
          totals={totals.data}
          pending={pending.data}
          reports={reports.data?.results}
          registered={registered.data?.count}
          onOpen={openTab}
        />
      )}

      <Tabs value={tab} onValueChange={(value) => openTab(value as ComplianceTab)}>
        <TabsList aria-label={t('page.sections')}>
          <TabsTrigger value="invoices">{t('tabs.invoices')}</TabsTrigger>
          <TabsTrigger value="sire">{t('tabs.sire')}</TabsTrigger>
          <TabsTrigger value="tra">{t('tabs.tra')}</TabsTrigger>
          <TabsTrigger value="pending">
            {t('tabs.pending')}
            {pendingCount > 0 && (
              <span className="num rounded-full bg-warning-soft px-1.5 text-2xs font-bold text-warning-ink">{pendingCount}</span>
            )}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="invoices">
          <InvoicesTab businessDate={property?.business_date} onOpenInvoice={openInvoice} />
        </TabsContent>
        <TabsContent value="sire">
          <SireTab
            key={pending.data ? 'ready' : 'loading'}
            businessDate={property?.business_date}
            reports={reports.data?.results ?? []}
            unreportedDays={pending.data?.sire.unreported_days ?? []}
            mode={sireMode}
            isLoading={reports.isPending}
            error={reports.isError ? reports.error : null}
            onRetry={() => void reports.refetch()}
            openReport={reportId}
            onOpenReport={openReport}
          />
        </TabsContent>
        <TabsContent value="tra">
          <TraTab key={traStatus ?? 'all'} initialStatus={traStatus ?? undefined} />
        </TabsContent>
        <TabsContent value="pending">
          {pending.isPending ? (
            <LoadingState variant="rows" rows={6} />
          ) : pending.isError ? (
            <ErrorState error={pending.error} onRetry={() => void pending.refetch()} />
          ) : (
            <PendingTab pending={pending.data} sireMode={sireMode} onOpenInvoice={openInvoice} onOpenReport={openReport} />
          )}
        </TabsContent>
      </Tabs>
      <InvoiceSheet invoiceId={invoiceId} onOpenChange={(open) => !open && openInvoice(null)} />
    </div>
  )
}
