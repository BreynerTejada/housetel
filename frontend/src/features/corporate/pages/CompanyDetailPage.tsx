import { Building2, EllipsisVertical, Mail, MapPin, Pencil, Phone, Trash2, UserRound } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { StatusBadge } from '@/components/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatDate, formatDateRange, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { toCents } from '@/features/finance/money'
import { useCompany, useCompanyReservations, useDeleteCompany, type Company } from '../api'
import { CompanyFormDialog } from '../components/CompanyFormDialog'
import { CreditMeter } from '../components/CreditMeter'
import { StatementPanel } from '../components/StatementPanel'

const TABS = ['statement', 'reservations', 'details'] as const
type Tab = (typeof TABS)[number]

export default function CompanyDetailPage() {
  const { id = '' } = useParams()
  const { t } = useTranslation('corporate')
  const company = useCompany(id)
  if (company.isPending) return <LoadingState />
  if (company.isError) return <ErrorState error={company.error} onRetry={() => void company.refetch()} />
  return (
    // grid-cols-1 = minmax(0, 1fr): on phones the tab row scrolls inside the gutter instead of widening the page.
    <div className="mx-auto grid w-full max-w-6xl grid-cols-1 gap-5">
      <nav aria-label={t('detail.breadcrumb')} className="text-[13px] text-muted">
        <Link to="/app/companies" className="rounded-sm hover:text-fg hover:underline">
          {t('nav.companies')}
        </Link>
      </nav>
      <CompanyProfile key={company.data.id} company={company.data} />
    </div>
  )
}

function CompanyProfile({ company }: { company: Company }) {
  const { t } = useTranslation('corporate')
  const navigate = useNavigate()
  const canManage = useCan('corporate.manage')
  const remove = useDeleteCompany()
  const [params, setParams] = useSearchParams()
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const requested = params.get('tab') as Tab | null
  const tab: Tab = requested && TABS.includes(requested) ? requested : 'statement'

  return (
    <>
      <header className="grid gap-5 rounded-xl border border-border bg-surface p-5 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-4">
            <span
              aria-hidden
              className="hidden size-12 shrink-0 place-items-center rounded-xl border border-border bg-surface-2 text-muted sm:grid"
            >
              <Building2 className="size-5" />
            </span>
            <div className="min-w-0">
              <p className="eyebrow flex flex-wrap items-center gap-x-2">
                <span>{t(`kinds.${company.kind}`)}</span>
                <span aria-hidden>·</span>
                <span>{company.credit_enabled ? t('detail.creditTerms', { count: company.payment_terms_days }) : t('list.noCredit')}</span>
              </p>
              <h1 className="mt-1 text-[22px] leading-7 tracking-[-0.025em] text-fg">{company.legal_name}</h1>
              <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted">
                <span className="num font-semibold text-fg">NIT {company.nit_display}</span>
                {company.trade_name && <span>· {company.trade_name}</span>}
                <span>· {company.vat_responsible ? t('detail.vatResponsible') : t('detail.notVatResponsible')}</span>
                {company.tax_responsibilities.map((code) => (
                  <Badge key={code} tone="outline" className="num" title={t(`responsibilities.${code}`)}>
                    {code}
                  </Badge>
                ))}
                {!company.is_active && <Badge tone="stone">{t('badges.inactive')}</Badge>}
              </p>
            </div>
          </div>
          {canManage && (
            <div className="flex items-center gap-2">
              <Button onClick={() => setEditing(true)}>
                <Pencil aria-hidden />
                {t('detail.edit')}
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="secondary" size="icon" aria-label={t('detail.actions')}>
                    <EllipsisVertical aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem destructive onSelect={() => setDeleting(true)}>
                    <Trash2 aria-hidden />
                    {t('detail.delete')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          )}
        </div>
        {company.credit && <CreditMeter credit={company.credit} />}
      </header>

      <Tabs value={tab} onValueChange={(value) => setParams(value === 'statement' ? {} : { tab: value }, { replace: true })}>
        <TabsList>
          <TabsTrigger value="statement">{t('detail.tabs.statement')}</TabsTrigger>
          <TabsTrigger value="reservations">{t('detail.tabs.reservations')}</TabsTrigger>
          <TabsTrigger value="details">{t('detail.tabs.details')}</TabsTrigger>
        </TabsList>
        <TabsContent value="statement">
          <StatementPanel companyId={company.id} />
        </TabsContent>
        <TabsContent value="reservations">
          <ReservationsPanel companyId={company.id} active={tab === 'reservations'} />
        </TabsContent>
        <TabsContent value="details">
          <DetailsPanel company={company} />
        </TabsContent>
      </Tabs>

      <CompanyFormDialog open={editing} onOpenChange={setEditing} company={company} />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={t('delete.title', { name: company.legal_name })}
        description={t('delete.description')}
        confirmLabel={t('delete.confirm')}
        onConfirm={async () => {
          await remove.mutateAsync(company.id)
          toast.success(t('delete.done'))
          navigate('/app/companies')
        }}
      />
    </>
  )
}

function ReservationsPanel({ companyId, active }: { companyId: string; active: boolean }) {
  const { t, i18n } = useTranslation('corporate')
  const lang = normalizeLang(i18n.language)
  const reservations = useCompanyReservations(companyId, active)
  if (reservations.isPending) return <LoadingState variant="rows" rows={4} />
  if (reservations.isError) return <ErrorState error={reservations.error} onRetry={() => void reservations.refetch()} />
  if (reservations.data.length === 0) {
    return <EmptyState icon={Building2} title={t('reservations.empty')} description={t('reservations.emptyHint')} />
  }
  return (
    <ul className="grid divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-xs">
      {reservations.data.map((reservation) => (
        <li key={reservation.id} className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto] sm:items-center">
          <div className="grid min-w-0 gap-0.5">
            <p className="flex flex-wrap items-center gap-2 text-[13px]">
              <Link to={`/app/reservations/${reservation.id}?tab=corporate-billing`} className="num font-semibold text-fg hover:underline">
                {reservation.code}
              </Link>
              <StatusBadge kind="reservation" status={reservation.status} />
              {!reservation.billed_to_company && <Badge tone="outline">{t('reservations.notBilled')}</Badge>}
            </p>
            <p className="truncate text-xs text-muted">
              {reservation.guest_name} · {formatDateRange(reservation.checkin_date, reservation.checkout_date, lang)}
              {reservation.purchase_order && ` · ${t('reservations.po', { po: reservation.purchase_order })}`}
              {reservation.invoice_number && ` · ${reservation.invoice_number}`}
            </p>
            {reservation.routing.length > 0 && (
              <p className="flex flex-wrap gap-1">
                {reservation.routing.map((route) => (
                  <Badge key={route} tone="neutral">
                    {t(`routes.${route}`)}
                  </Badge>
                ))}
              </p>
            )}
          </div>
          <MoneyText
            value={reservation.company_balance}
            className={cn('text-sm font-semibold sm:text-right', toCents(reservation.company_balance) === 0 && 'text-subtle')}
          />
        </li>
      ))}
    </ul>
  )
}

function DetailsPanel({ company }: { company: Company }) {
  const { t, i18n } = useTranslation('corporate')
  const lang = normalizeLang(i18n.language)
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card title={t('detail.billing')}>
        <Row icon={Mail} label={t('fields.billingEmail')} value={company.billing_email} />
        <Row icon={Phone} label={t('fields.phone')} value={company.phone} />
        <Row
          icon={MapPin}
          label={t('fields.address')}
          value={[company.address, company.city, company.department].filter(Boolean).join(', ')}
        />
        {company.notes && <p className="rounded-md bg-surface-2 px-3 py-2 text-[13px] whitespace-pre-line text-muted">{company.notes}</p>}
        <p className="text-xs text-subtle">{t('detail.updated', { date: formatDate(company.updated_at, undefined, lang) })}</p>
      </Card>
      <Card title={t('detail.contacts')}>
        {company.contacts.length === 0 ? (
          <p className="text-[13px] text-muted">{t('form.noContacts')}</p>
        ) : (
          <ul className="grid gap-3">
            {company.contacts.map((contact, index) => (
              <li key={`${contact.name}-${index}`} className="flex gap-3 text-[13px]">
                <UserRound aria-hidden className="mt-0.5 size-4 shrink-0 text-muted" />
                <span className="grid min-w-0">
                  <span className="font-semibold text-fg">
                    {contact.name}
                    {contact.role && <span className="font-normal text-muted"> · {contact.role}</span>}
                  </span>
                  {contact.email && (
                    <a href={`mailto:${contact.email}`} className="truncate text-muted hover:text-fg hover:underline">
                      {contact.email}
                    </a>
                  )}
                  {contact.phone && <span className="num text-muted">{contact.phone}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid content-start gap-3 rounded-xl border border-border bg-surface p-5 shadow-xs">
      <h2 className="text-[15px] font-bold">{title}</h2>
      {children}
    </section>
  )
}

function Row({ icon: Icon, label, value }: { icon: typeof Mail; label: string; value: string }) {
  return (
    <div className="flex gap-3 text-[13px]">
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-muted" />
      <span className="grid min-w-0">
        <span className="text-xs text-muted">{label}</span>
        <span className={cn('break-words', value ? 'text-fg' : 'text-subtle')}>{value || '—'}</span>
      </span>
    </div>
  )
}
