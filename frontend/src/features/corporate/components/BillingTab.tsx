import { Building2, CircleAlert, Plus, UserRound } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Combobox } from '@/components/ui/combobox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { moneyLabel, toCents } from '@/features/finance/money'
import {
  ROUTES,
  useCompanies,
  useReservationBilling,
  useSaveBilling,
  type BillTo,
  type Company,
  type ReservationBilling,
  type Route,
} from '../api'
import { CompanyFormDialog } from './CompanyFormDialog'
import { CreditMeter } from './CreditMeter'

/** Reservation tab "Facturación": who pays the stay and which charges go to the company's folio. */
export function BillingTab({ reservationId }: { reservationId: string }) {
  const billing = useReservationBilling(reservationId)
  if (billing.isPending) return <LoadingState variant="rows" rows={4} />
  if (billing.isError) return <ErrorState error={billing.error} onRetry={() => void billing.refetch()} />
  // keyed by the saved state: the form starts again from the server after each save
  return <BillingEditor key={billing.data.billing.updated_at ?? 'new'} reservationId={reservationId} data={billing.data} />
}

function BillingEditor({ reservationId, data }: { reservationId: string; data: ReservationBilling }) {
  const { t } = useTranslation('corporate')
  const canManage = useCan('corporate.manage')
  const save = useSaveBilling(reservationId)
  const companies = useCompanies({ active: true, page_size: 200 }, canManage)
  const [billTo, setBillTo] = useState<BillTo>(data.billing.bill_to)
  const [companyId, setCompanyId] = useState<string | null>(data.billing.company?.id ?? null)
  const [routing, setRouting] = useState<Route[]>(data.billing.routing.length ? data.billing.routing : ['all'])
  const [po, setPo] = useState(data.billing.purchase_order)
  const [notes, setNotes] = useState(data.billing.notes)
  const [moveExisting, setMoveExisting] = useState(true)
  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState<Company | null>(null)
  const [error, setError] = useState<string | null>(null)

  const options = useMemo(() => {
    const list = [...(companies.data?.results ?? [])]
    if (created && !list.some((company) => company.id === created.id)) list.unshift(created)
    const current = data.billing.company
    const rows = list.map((company) => ({
      value: company.id,
      label: company.trade_name ? `${company.legal_name} · ${company.trade_name}` : company.legal_name,
      description: `NIT ${company.nit_display}${company.credit_enabled ? ` · ${t('billing.creditDays', { count: company.payment_terms_days })}` : ''}`,
      keywords: [company.nit, company.trade_name].filter(Boolean),
    }))
    if (current && !rows.some((row) => row.value === current.id)) {
      rows.unshift({ value: current.id, label: current.legal_name, description: `NIT ${current.nit_display}`, keywords: [current.nit] })
    }
    return rows
  }, [companies.data, created, data.billing.company, t])

  const dirty =
    billTo !== data.billing.bill_to ||
    (billTo === 'company' &&
      (companyId !== (data.billing.company?.id ?? null) ||
        routing.join() !== (data.billing.routing.length ? data.billing.routing : ['all']).join() ||
        po !== data.billing.purchase_order)) ||
    notes !== data.billing.notes
  const valid = billTo === 'guest' || (Boolean(companyId) && routing.length > 0)

  function toggleRoute(route: Route, checked: boolean) {
    if (route === 'all') {
      setRouting(checked ? ['all'] : ['lodging'])
      return
    }
    setRouting((current) => {
      const next = current.filter((item) => item !== 'all' && item !== route)
      return checked ? ROUTES.filter((item) => item === route || next.includes(item)) : next
    })
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!dirty || !valid) return
    setError(null)
    try {
      const result = await save.mutateAsync({
        bill_to: billTo,
        company_id: billTo === 'company' ? companyId : null,
        routing: billTo === 'company' ? routing : [],
        purchase_order: billTo === 'company' ? po.trim() : '',
        notes: notes.trim(),
        move_existing: moveExisting,
      })
      toast.success(
        result.moved
          ? t('billing.savedMoved', { count: result.moved })
          : billTo === 'company'
            ? t('billing.savedCompany', { company: result.billing.company?.legal_name ?? '' })
            : t('billing.savedGuest'),
      )
    } catch (err) {
      setError(errorMessage(err, t))
    }
  }

  const booker = data.reservation.booker
  return (
    <div className="grid min-w-0 grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <form onSubmit={submit} className="grid min-w-0 grid-cols-1 gap-6 rounded-xl border border-border bg-surface p-5 shadow-xs" noValidate>
        <fieldset className="grid min-w-0 gap-3" disabled={!canManage}>
          <legend className="mb-1 text-[15px] font-bold">{t('billing.who')}</legend>
          <RadioGroup value={billTo} onValueChange={(value) => setBillTo(value as BillTo)} className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <ChoiceCard
              value="guest"
              selected={billTo === 'guest'}
              icon={UserRound}
              title={t('billing.guest')}
              detail={[booker.full_name, booker.document_number && `${booker.document_type} ${booker.document_number}`]
                .filter(Boolean)
                .join(' · ')}
            />
            <ChoiceCard
              value="company"
              selected={billTo === 'company'}
              icon={Building2}
              title={t('billing.company')}
              detail={data.billing.company?.legal_name ?? t('billing.companyHint')}
            />
          </RadioGroup>
        </fieldset>

        {billTo === 'company' && (
          <>
            <div className="grid min-w-0 grid-cols-1 gap-1.5">
              <Label htmlFor="billing-company">{t('billing.companyLabel')}</Label>
              <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
                <Combobox
                  id="billing-company"
                  options={options}
                  value={companyId}
                  onChange={setCompanyId}
                  disabled={!canManage}
                  placeholder={companies.isPending && canManage ? t('billing.loadingCompanies') : t('billing.pickCompany')}
                  searchPlaceholder={t('billing.searchCompany')}
                  emptyText={t('billing.noCompany')}
                  className="min-w-0 flex-1"
                />
                {canManage && (
                  <Button variant="secondary" onClick={() => setCreating(true)}>
                    <Plus aria-hidden />
                    {t('billing.newCompany')}
                  </Button>
                )}
              </div>
            </div>

            <fieldset className="grid min-w-0 gap-2" disabled={!canManage}>
              <legend className="mb-1 text-[13px] font-semibold text-fg">{t('billing.routing')}</legend>
              <p className="-mt-1 mb-1 text-xs text-muted">{t('billing.routingHint')}</p>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {ROUTES.map((route) => {
                  const checked = routing.includes(route) || (route !== 'all' && routing.includes('all'))
                  return (
                    <label
                      key={route}
                      className={cn(
                        'flex cursor-pointer gap-2.5 rounded-lg border p-3 text-[13px] transition-colors has-[:disabled]:cursor-default',
                        checked ? 'border-accent/45 bg-accent-soft/60' : 'border-border hover:border-border-strong',
                      )}
                    >
                      <Checkbox
                        checked={checked}
                        disabled={!canManage || (route !== 'all' && routing.includes('all'))}
                        onCheckedChange={(value) => toggleRoute(route, value === true)}
                        className="mt-0.5"
                      />
                      <span className="grid gap-0.5">
                        <span className="font-semibold text-fg">{t(`routes.${route}`)}</span>
                        <span className="text-xs text-muted">{t(`routes.${route}Hint`)}</span>
                      </span>
                    </label>
                  )
                })}
              </div>
            </fieldset>

            <div className="grid gap-1.5 sm:max-w-sm">
              <Label htmlFor="billing-po">{t('billing.po')}</Label>
              <Input
                id="billing-po"
                autoComplete="off"
                maxLength={60}
                value={po}
                disabled={!canManage}
                placeholder="OC-4521"
                onChange={(event) => setPo(event.target.value)}
              />
            </div>
          </>
        )}

        <div className="grid gap-1.5">
          <Label htmlFor="billing-notes">{t('billing.notes')}</Label>
          <Textarea
            id="billing-notes"
            rows={2}
            maxLength={2000}
            value={notes}
            disabled={!canManage}
            placeholder={t('billing.notesPlaceholder')}
            onChange={(event) => setNotes(event.target.value)}
          />
        </div>

        {canManage && (
          <div className="grid gap-3 border-t border-border pt-4 sm:flex sm:items-center sm:justify-between">
            <label className="flex items-start gap-2 text-[13px]">
              <Checkbox checked={moveExisting} onCheckedChange={(value) => setMoveExisting(value === true)} className="mt-0.5" />
              <span>
                <span className="font-semibold text-fg">{t('billing.moveExisting')}</span>
                <span className="block text-xs text-muted">{t('billing.moveExistingHint')}</span>
              </span>
            </label>
            <Button type="submit" variant="primary" disabled={!dirty || !valid} loading={save.isPending} className="w-full sm:w-auto">
              {t('billing.save')}
            </Button>
          </div>
        )}
        {error && (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
            {error}
          </p>
        )}
      </form>

      <Summary data={data} reservationId={reservationId} />

      <CompanyFormDialog
        open={creating}
        onOpenChange={setCreating}
        onSaved={(company) => {
          setCreated(company)
          setCompanyId(company.id)
        }}
      />
    </div>
  )
}

function ChoiceCard({
  value,
  selected,
  icon: Icon,
  title,
  detail,
}: {
  value: BillTo
  selected: boolean
  icon: typeof UserRound
  title: string
  detail: string
}) {
  return (
    <label
      className={cn(
        'flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors has-[:disabled]:cursor-default',
        selected ? 'border-accent/50 bg-accent-soft/60' : 'border-border hover:border-border-strong',
      )}
    >
      <RadioGroupItem value={value} className="mt-1" />
      <Icon aria-hidden className={cn('mt-0.5 size-4 shrink-0', selected ? 'text-accent-ink' : 'text-muted')} />
      <span className="grid min-w-0 gap-0.5">
        <span className="text-[13px] font-semibold text-fg">{title}</span>
        <span className="truncate text-xs text-muted">{detail}</span>
      </span>
    </label>
  )
}

/** Who pays what right now: the guest's part, each company's part and what blocks the check-out. */
function Summary({ data, reservationId }: { data: ReservationBilling; reservationId: string }) {
  const { t } = useTranslation('corporate')
  const { balances } = data
  const blocking = balances.companies.filter((part) => part.blocks_checkout)
  return (
    <aside aria-label={t('billing.summary')} className="grid content-start gap-4 rounded-xl border border-border bg-surface p-5 shadow-xs">
      <h3 className="text-[15px] font-bold">{t('billing.summary')}</h3>
      <dl className="grid gap-3 text-[13px]">
        <div className="flex items-baseline justify-between gap-3">
          <dt className="flex items-center gap-2 text-muted">
            <UserRound aria-hidden className="size-4" />
            {t('billing.guestPart')}
          </dt>
          <dd className="font-semibold">
            <MoneyText value={balances.guest} />
          </dd>
        </div>
        {balances.companies.map((part) => (
          <div key={part.company.id} className="grid gap-1">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="flex min-w-0 items-center gap-2 text-muted">
                <Building2 aria-hidden className="size-4 shrink-0" />
                <Link to={`/app/companies/${part.company.id}`} className="truncate hover:text-fg hover:underline">
                  {part.company.trade_name || part.company.legal_name}
                </Link>
              </dt>
              <dd className="font-semibold">
                <MoneyText value={part.expected} />
              </dd>
            </div>
            <Badge tone={part.credit ? 'info' : 'warning'} className="justify-self-end">
              {part.credit ? t('billing.onCredit') : t('billing.noCredit')}
            </Badge>
          </div>
        ))}
        <div className="flex items-baseline justify-between gap-3 border-t border-border pt-3">
          <dt className="font-semibold text-fg">{t('billing.checkoutDue')}</dt>
          <dd className="text-[15px] font-bold">
            <MoneyText value={balances.checkout_due} highlightNegative />
          </dd>
        </div>
      </dl>
      {blocking.length > 0 && (
        <p className="flex gap-2 rounded-lg bg-warning-soft px-3 py-2 text-xs text-warning-ink">
          <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t('billing.blocksCheckout', { company: blocking.map((part) => part.company.legal_name).join(', ') })}
        </p>
      )}
      {data.credit && data.billing.company && (
        <div className="grid gap-1.5">
          <p className="text-xs font-semibold text-muted">{t('billing.creditOf', { company: data.billing.company.legal_name })}</p>
          <CreditMeter credit={data.credit} />
        </div>
      )}
      {toCents(balances.guest) < 0 && (
        <p className="rounded-lg bg-info-soft px-3 py-2 text-xs text-info-ink">
          {t('billing.guestCredit', { amount: moneyLabel(String(-toCents(balances.guest) / 100)) })}
        </p>
      )}
      <Button asChild variant="secondary" size="sm" className="w-fit">
        <Link to={`/app/reservations/${reservationId}?tab=folio`}>{t('billing.openFolios', { count: data.folios.length })}</Link>
      </Button>
    </aside>
  )
}
