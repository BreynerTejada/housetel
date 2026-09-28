import type { PaginationState } from '@tanstack/react-table'
import { Check, Copy, PlayCircle, PlugZap, Receipt, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { errorMessage } from '@/lib/errors'
import { formatMoney, formatRelative, normalizeLang } from '@/lib/format'
import { useRuntimeConfig } from '@/lib/runtime'
import { cn } from '@/lib/utils'
import {
  useAdminInvoices,
  useBillingSettings,
  useRunBillingCycle,
  useTestBillingSettings,
  useUpdateBillingSettings,
  type BillingSettings,
} from '../../api'
import { AdminInvoiceActions } from '../../components/AdminInvoiceActions'
import { InvoicesTable } from '../../components/InvoicesTable'

const ALL = 'all'
const STATUSES = ['open', 'failed', 'paid', 'void'] as const
const KINDS = ['subscription', 'commissions', 'other'] as const

/** `/admin/billing`: every platform invoice, the daily billing cycle and the platform's charging account. */
export default function AdminBillingPage() {
  const { t } = useTranslation('saas')
  const [status, setStatus] = useState<string>(ALL)
  const [kind, setKind] = useState<string>(ALL)
  const [q, setQ] = useState('')
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 })
  const invoices = useAdminInvoices({
    status: status === ALL ? undefined : status,
    kind: kind === ALL ? undefined : kind,
    q: q.trim() || undefined,
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
  })
  const summary = invoices.data?.summary

  function resetPage() {
    setPagination((current) => ({ ...current, pageIndex: 0 }))
  }

  return (
    <div className="mx-auto grid grid-cols-1 w-full max-w-7xl gap-6">
      <PageHeader title={t('admin.billing.title')} description={t('admin.billing.description')} className="pb-0" actions={<RunCycleButton />} />

      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:max-w-2xl">
        <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
          <dt className="text-[13px] font-semibold text-muted">{t('admin.billing.openTotal')}</dt>
          <dd className="mt-1.5 text-[24px] leading-7 font-semibold tracking-[-0.02em] text-fg">{summary ? formatMoney(summary.open_total) : '—'}</dd>
        </div>
        <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
          <dt className="text-[13px] font-semibold text-muted">{t('admin.billing.paidMonth')}</dt>
          <dd className="mt-1.5 text-[24px] leading-7 font-semibold tracking-[-0.02em] text-fg">{summary ? formatMoney(summary.paid_month) : '—'}</dd>
        </div>
      </dl>

      {invoices.isError ? (
        <ErrorState error={invoices.error} onRetry={() => void invoices.refetch()} />
      ) : (
        <InvoicesTable
          invoices={invoices.data?.results ?? []}
          isLoading={invoices.isPending}
          admin
          showOrganization
          server={{ rowCount: invoices.data?.count ?? 0, pagination, onPaginationChange: setPagination }}
          search={q}
          onSearchChange={(value) => {
            setQ(value)
            resetPage()
          }}
          actions={(invoice) => <AdminInvoiceActions invoice={invoice} />}
          empty={<EmptyState icon={Receipt} title={t('admin.billing.empty')} />}
          toolbar={
            <div className="flex flex-wrap gap-2">
              <Select
                name="status"
                value={status}
                onValueChange={(value) => {
                  setStatus(value)
                  resetPage()
                }}
              >
                <SelectTrigger className="w-48" aria-label={t('invoices.status')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>{t('admin.billing.allStatuses')}</SelectItem>
                  {STATUSES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {t(`status.invoice.${value}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                name="kind"
                value={kind}
                onValueChange={(value) => {
                  setKind(value)
                  resetPage()
                }}
              >
                <SelectTrigger className="w-56" aria-label={t('invoices.concept')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>{t('admin.billing.allKinds')}</SelectItem>
                  {KINDS.map((value) => (
                    <SelectItem key={value} value={value}>
                      {t(`invoices.kind.${value}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          }
        />
      )}

      <PlatformAccount />
    </div>
  )
}

function RunCycleButton() {
  const { t } = useTranslation('saas')
  const run = useRunBillingCycle()
  return (
    <ConfirmDialog
      trigger={
        <Button variant="secondary">
          <PlayCircle aria-hidden />
          {t('admin.billing.runCycle')}
        </Button>
      }
      title={t('admin.billing.runCycleTitle')}
      description={t('admin.billing.runCycleText')}
      confirmLabel={t('admin.billing.runCycle')}
      onConfirm={async () => {
        const result = await run.mutateAsync()
        if (result.status === 'failed') toast.error(result.summary || t('admin.billing.cycleFailed'))
        else toast.success(t('admin.billing.cycleDone'), { description: result.summary })
      }}
    />
  )
}

function PlatformAccount() {
  const { t } = useTranslation('saas')
  const settings = useBillingSettings()
  return (
    <section className="grid grid-cols-1 gap-4 rounded-xl border border-border bg-surface p-5 shadow-xs sm:p-6">
      <div>
        <h2 className="flex items-center gap-2 text-[15px] font-bold text-fg">
          <PlugZap aria-hidden className="size-4 text-subtle" />
          {t('admin.billing.accountTitle')}
        </h2>
        <p className="mt-0.5 max-w-2xl text-sm text-muted">{t('admin.billing.accountText')}</p>
      </div>
      {settings.isPending ? (
        <LoadingState />
      ) : settings.isError ? (
        <ErrorState error={settings.error} onRetry={() => void settings.refetch()} className="py-6" />
      ) : (
        <AccountSettings settings={settings.data} />
      )}
    </section>
  )
}

function AccountSettings({ settings }: { settings: BillingSettings }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const update = useUpdateBillingSettings()
  const test = useTestBillingSettings()
  const [copied, setCopied] = useState(false)
  const { simulations_enabled: simulations } = useRuntimeConfig()
  const wompi = settings.wompi
  const credentials = [
    ['public_key_configured', 'WOMPI_PLATFORM_PUBLIC_KEY'],
    ['private_key_configured', 'WOMPI_PLATFORM_PRIVATE_KEY'],
    ['integrity_secret_configured', 'WOMPI_PLATFORM_INTEGRITY_SECRET'],
    ['events_secret_configured', 'WOMPI_PLATFORM_EVENTS_SECRET'],
  ] as const
  const allConfigured = credentials.every(([key]) => wompi[key])

  async function copyWebhook() {
    try {
      await navigator.clipboard.writeText(wompi.webhook_url)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(t('admin.billing.copyFailed'))
    }
  }

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <div className="grid grid-cols-1 content-start gap-3">
        <p className="text-sm font-semibold text-fg">{t('admin.billing.mode')}</p>
        <ToggleGroup
          type="single"
          value={settings.mode}
          onValueChange={(value) =>
            value &&
            update
              .mutateAsync({ mode: value as BillingSettings['mode'] })
              .then(() => toast.success(value === 'real' ? t('admin.billing.modeReal') : t('admin.billing.modeSimulated')))
              .catch((error: unknown) => toast.error(errorMessage(error, t)))
          }
          aria-label={t('admin.billing.mode')}
          className="w-fit"
          disabled={update.isPending}
        >
          <ToggleGroupItem value="simulated" disabled={!simulations && settings.mode !== 'simulated'} title={simulations ? undefined : t('admin.billing.simulatedOff')}>
            {t('admin.billing.simulated')}
          </ToggleGroupItem>
          <ToggleGroupItem value="real">{t('admin.billing.real')}</ToggleGroupItem>
        </ToggleGroup>
        <p className="text-sm text-muted">{settings.mode === 'real' ? t('admin.billing.realHint') : t('admin.billing.simulatedHint')}</p>
        <label className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
          <span className="grid gap-0.5">
            <span className="text-sm font-semibold text-fg">{t('admin.billing.enabled')}</span>
            <span className="text-xs text-muted">{t('admin.billing.enabledHint')}</span>
          </span>
          <Switch
            checked={settings.enabled}
            disabled={update.isPending}
            onCheckedChange={(enabled) =>
              update
                .mutateAsync({ enabled })
                .then(() => toast.success(enabled ? t('admin.billing.enabledOn') : t('admin.billing.enabledOff')))
                .catch((error: unknown) => toast.error(errorMessage(error, t)))
            }
          />
        </label>
        {settings.mode === 'real' && !allConfigured && (
          <p className="rounded-md bg-warning-soft px-3 py-2 text-sm text-warning-ink">{t('admin.billing.missingCredentials')}</p>
        )}
        {settings.collection_available === false && (
          <p role="status" className="rounded-md bg-warning-soft px-3 py-2 text-sm text-warning-ink">
            {t('admin.billing.collectionStopped')}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            loading={test.isPending}
            onClick={() =>
              test
                .mutateAsync()
                .then((result) =>
                  result.status === 'ok' ? toast.success(result.status_message || t('admin.billing.testOk')) : toast.error(result.status_message || t('admin.billing.testFailed')),
                )
                .catch((error: unknown) => toast.error(errorMessage(error, t)))
            }
          >
            {t('admin.billing.test')}
          </Button>
          {settings.status !== 'unknown' && (
            <Badge tone={settings.status === 'ok' ? 'success' : 'danger'}>
              {settings.status === 'ok' ? t('admin.billing.statusOk') : t('admin.billing.statusError')}
            </Badge>
          )}
          {settings.last_checked_at && (
            <span className="text-xs text-muted">{t('admin.billing.lastChecked', { when: formatRelative(settings.last_checked_at, lang) })}</span>
          )}
        </div>
        {settings.status_message && <p className="text-xs text-muted">{settings.status_message}</p>}
      </div>

      <div className="grid grid-cols-1 content-start gap-3">
        <p className="text-sm font-semibold text-fg">
          {t('admin.billing.credentials')}
          <span className="ml-2 font-normal text-muted">({wompi.environment})</span>
        </p>
        <ul className="grid grid-cols-1 gap-1.5 text-sm">
          {credentials.map(([key, name]) => (
            <li key={key} className="flex items-center justify-between gap-3 rounded-md bg-surface-2 px-3 py-1.5">
              <code className="num truncate text-xs text-fg">{name}</code>
              <span className={cn('inline-flex items-center gap-1 text-xs font-semibold', wompi[key] ? 'text-success-ink' : 'text-muted')}>
                {wompi[key] ? <Check aria-hidden className="size-3.5" /> : <X aria-hidden className="size-3.5" />}
                {wompi[key] ? t('admin.billing.configured') : t('admin.billing.notConfigured')}
              </span>
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted">{t('admin.billing.envHint')}</p>
        <div className="grid grid-cols-1 gap-1">
          <p className="text-xs font-semibold text-muted">{t('admin.billing.webhook')}</p>
          <div className="flex items-center gap-2">
            <code className="num min-w-0 flex-1 truncate rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-xs text-fg">{wompi.webhook_url}</code>
            <Button variant="ghost" size="icon-sm" aria-label={t('admin.billing.copyWebhook')} onClick={() => void copyWebhook()}>
              {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
