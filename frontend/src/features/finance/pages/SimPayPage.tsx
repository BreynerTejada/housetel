import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleCheck, CircleX, Clock3, CreditCard, FlaskConical, Landmark, LockKeyhole, SearchX, Smartphone } from 'lucide-react'
import { useCallback, useEffect, useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { formatRelative, normalizeLang } from '@/lib/format'
import { currentLanguage, LANGUAGES, setLanguage } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { decideSimIntent, financeKeys, getSimIntent, type SimIntent, type SimMethod, type SimOutcome } from '../api'
import { moneyLabel } from '../money'
import { leavePage } from '../navigation'

const METHODS: { value: SimMethod; icon: typeof CreditCard }[] = [
  { value: 'card', icon: CreditCard },
  { value: 'pse', icon: Landmark },
  { value: 'nequi', icon: Smartphone },
]
const RETURN_SECONDS = 5
const OPEN_STATUSES = ['created', 'pending', 'error']

/**
 * `/sim/pay/:reference` — the simulated payment gateway. It looks and behaves like a real checkout
 * (merchant, amount, card / PSE / Nequi) but a hatched "Simulation mode" band stays on top: nobody is
 * charged, the person chooses the outcome.
 */
export default function SimPayPage() {
  const { reference = '' } = useParams()
  const { t } = useTranslation('finance')
  const intent = useQuery({ queryKey: financeKeys.simIntent(reference), queryFn: () => getSimIntent(reference), retry: false })

  return (
    <div className="min-h-dvh bg-bg">
      <SimulationBand />
      <div className="mx-auto w-full max-w-[460px] px-4 pt-6 pb-12">
        <div className="mb-4 flex items-center justify-between gap-3">
          <span className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-muted">
            <LockKeyhole aria-hidden className="size-4" />
            {t('sim.checkout')}
          </span>
          <LanguageToggle />
        </div>
        {intent.isPending ? (
          <LoadingState className="rounded-2xl border border-border bg-surface" />
        ) : intent.isError ? (
          isApiError(intent.error) && intent.error.status === 404 ? (
            <Card>
              <Outcome icon={SearchX} tone="stone" title={t('sim.notFound')} description={t('sim.notFoundHint')} />
            </Card>
          ) : (
            <Card>
              <ErrorState error={intent.error} onRetry={() => intent.refetch()} />
            </Card>
          )
        ) : (
          <Checkout intent={intent.data} reference={reference} />
        )}
        <p className="mt-5 text-center text-xs leading-5 text-muted">{t('sim.footer')}</p>
      </div>
    </div>
  )
}

/** The hatched tape across the top of the page: impossible to miss, stays while scrolling. */
function SimulationBand() {
  const { t } = useTranslation('finance')
  return (
    <div
      role="status"
      aria-label={t('sim.band')}
      className="hatch sticky top-0 z-20 border-b border-warning/40 bg-warning-soft text-warning-ink"
    >
      <p className="mx-auto flex max-w-3xl flex-wrap items-center justify-center gap-x-2 gap-y-0.5 px-4 py-2 text-center text-[13px]">
        <FlaskConical aria-hidden className="size-4" />
        <strong className="font-extrabold tracking-[0.08em] uppercase">{t('sim.band')}</strong>
        <span aria-hidden className="hidden sm:inline">
          ·
        </span>
        <span className="font-medium">{t('sim.bandText')}</span>
      </p>
    </div>
  )
}

function LanguageToggle() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const active = currentLanguage()
  return (
    <div className="inline-flex rounded-md border border-border bg-surface p-0.5 text-xs font-bold">
      {LANGUAGES.map((lang) => (
        <button
          key={lang}
          type="button"
          aria-label={t(`languages.${lang}`)}
          aria-pressed={active === lang}
          onClick={() => void setLanguage(lang, queryClient)}
          className={cn(
            'rounded px-2 py-1 uppercase transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
            active === lang ? 'bg-surface-3 text-fg' : 'text-muted hover:text-fg',
          )}
        >
          {lang}
        </button>
      ))}
    </div>
  )
}

function Card({ children }: { children: ReactNode }) {
  return <article className="overflow-hidden rounded-2xl border border-border bg-surface shadow-md">{children}</article>
}

function initials(name: string): string {
  const words = name.replace(/^(hotel|hostal|hostel)\s+/i, '').split(/\s+/).filter(Boolean)
  return words
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '')
    .join('')
}

function Checkout({ intent, reference }: { intent: SimIntent; reference: string }) {
  const { t, i18n } = useTranslation('finance')
  const lang = normalizeLang(i18n.language)
  const queryClient = useQueryClient()
  const [method, setMethod] = useState<SimMethod>('card')
  const [retrying, setRetrying] = useState(false)
  const decide = useMutation({
    mutationFn: (outcome: SimOutcome) => decideSimIntent(reference, outcome, method),
    onSuccess: (data) => {
      queryClient.setQueryData(financeKeys.simIntent(reference), data)
      setRetrying(false)
    },
    onError: () => void queryClient.invalidateQueries({ queryKey: financeKeys.simIntent(reference) }),
  })
  const hotel = intent.property.name
  const showForm = OPEN_STATUSES.includes(intent.status) || (intent.status === 'declined' && retrying)
  const brand = intent.property.primary_color || 'var(--accent)'

  return (
    <Card>
      <header className="grid gap-5 px-6 pt-6 pb-5">
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="grid size-11 shrink-0 place-items-center rounded-xl text-[15px] font-extrabold text-white shadow-xs"
            style={{ background: brand }}
          >
            {initials(hotel)}
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-lg leading-6 font-bold">{hotel}</h1>
            <p className="text-[13px] text-muted">
              {[intent.property.city, intent.reservation_code && t('sim.reservation', { code: intent.reservation_code })]
                .filter(Boolean)
                .join(' · ')}
            </p>
          </div>
        </div>
        <div>
          <p className="eyebrow">{t('sim.total')}</p>
          <p className="num mt-1 text-[36px] leading-10 font-semibold tracking-[-0.035em] text-fg">
            <MoneyText value={intent.amount} currency={intent.currency} />
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-3 text-[13px]">
          <div className="min-w-0">
            <dt className="text-muted">{t('sim.reference')}</dt>
            <dd className="num truncate font-semibold">{intent.reference}</dd>
          </div>
          {intent.expires_at && OPEN_STATUSES.includes(intent.status) && (
            <div>
              <dt className="text-muted">{t('sim.expires')}</dt>
              <dd className="font-semibold">{formatRelative(intent.expires_at, lang)}</dd>
            </div>
          )}
        </dl>
      </header>
      <div className="border-t border-border">
        {showForm ? (
          <PaymentForm
            method={method}
            onMethod={setMethod}
            payer={intent.payer_first_name}
            amountLabel={moneyLabel(intent.amount, intent.currency)}
            pending={decide.isPending ? decide.variables : null}
            error={decide.isError ? errorMessage(decide.error, t) : null}
            onDecide={(outcome) => decide.mutate(outcome)}
          />
        ) : (
          <Result intent={intent} hotel={hotel} onRetry={() => setRetrying(true)} />
        )}
      </div>
    </Card>
  )
}

function PaymentForm({
  method,
  onMethod,
  payer,
  amountLabel,
  pending,
  error,
  onDecide,
}: {
  method: SimMethod
  onMethod: (method: SimMethod) => void
  payer: string | null
  amountLabel: string
  pending: SimOutcome | null
  error: string | null
  onDecide: (outcome: SimOutcome) => void
}) {
  const { t } = useTranslation('finance')
  const ids = useId()
  const busy = pending !== null
  const field = (name: string, label: string, control: ReactNode, className?: string) => (
    <div className={cn('grid gap-1.5', className)}>
      <Label htmlFor={`${ids}-${name}`}>{label}</Label>
      {control}
    </div>
  )
  return (
    <div className="grid gap-5 px-6 pt-5 pb-6">
      <Tabs value={method} onValueChange={(value) => onMethod(value as SimMethod)}>
        <TabsList className="gap-6" aria-label={t('sim.methods')}>
          {METHODS.map(({ value, icon: Icon }) => (
            <TabsTrigger key={value} value={value}>
              <Icon aria-hidden />
              {t(`sim.method.${value}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="card" className="grid grid-cols-2 gap-4">
          {field(
            'number',
            t('sim.cardNumber'),
            <Input id={`${ids}-number`} name="card_number" inputMode="numeric" autoComplete="off" defaultValue="4242 4242 4242 4242" className="num" />,
            'col-span-2',
          )}
          {field('expiry', t('sim.cardExpiry'), <Input id={`${ids}-expiry`} name="card_expiry" autoComplete="off" defaultValue="12/30" className="num" />)}
          {field('cvc', t('sim.cardCvc'), <Input id={`${ids}-cvc`} name="card_cvc" autoComplete="off" defaultValue="123" className="num" />)}
          {field(
            'holder',
            t('sim.cardHolder'),
            <Input id={`${ids}-holder`} name="card_holder" autoComplete="off" defaultValue={(payer ?? '').toUpperCase()} />,
          )}
          {field(
            'installments',
            t('sim.installments'),
            <Select name="installments" defaultValue="1">
              <SelectTrigger id={`${ids}-installments`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[1, 2, 3, 6, 12, 24, 36].map((count) => (
                  <SelectItem key={count} value={String(count)}>
                    {t('sim.installmentsCount', { count })}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>,
          )}
        </TabsContent>
        <TabsContent value="pse" className="grid gap-4">
          <RadioGroup name="person_type" defaultValue="natural" aria-label={t('sim.personType')} className="flex gap-5">
            {(['natural', 'juridica'] as const).map((kind) => (
              <label key={kind} htmlFor={`${ids}-${kind}`} className="flex items-center gap-2 text-sm">
                <RadioGroupItem id={`${ids}-${kind}`} value={kind} />
                {t(`sim.person.${kind}`)}
              </label>
            ))}
          </RadioGroup>
          {field(
            'bank',
            t('sim.bank'),
            <Select name="bank" defaultValue="approve">
              <SelectTrigger id={`${ids}-bank`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="approve">{t('sim.bankApproves')}</SelectItem>
                <SelectItem value="decline">{t('sim.bankDeclines')}</SelectItem>
              </SelectContent>
            </Select>,
          )}
          {field('document', t('sim.document'), <Input id={`${ids}-document`} name="document" inputMode="numeric" autoComplete="off" defaultValue="1010101010" className="num" />)}
        </TabsContent>
        <TabsContent value="nequi" className="grid gap-4">
          {field('phone', t('sim.nequiPhone'), <Input id={`${ids}-phone`} name="nequi_phone" inputMode="tel" autoComplete="off" defaultValue="399 111 1111" className="num" />)}
          <p className="text-[13px] text-muted">{t('sim.nequiHint')}</p>
        </TabsContent>
      </Tabs>

      <p className="rounded-lg bg-surface-2 px-3 py-2.5 text-xs leading-5 text-muted">{t('sim.testData')}</p>

      {error && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {error}
        </p>
      )}

      <div className="grid gap-2">
        <Button type="button" variant="primary" size="lg" className="w-full" loading={pending === 'approved'} disabled={busy} onClick={() => onDecide('approved')}>
          {t('sim.pay', { amount: amountLabel })}
        </Button>
        <div className="grid grid-cols-2 gap-2">
          <Button type="button" variant="secondary" loading={pending === 'declined'} disabled={busy} onClick={() => onDecide('declined')}>
            {t('sim.decline')}
          </Button>
          <Button type="button" variant="ghost" loading={pending === 'expired'} disabled={busy} onClick={() => onDecide('expired')}>
            {t('sim.expire')}
          </Button>
        </div>
      </div>
    </div>
  )
}

const TONES = {
  success: 'bg-success-soft text-success-ink',
  danger: 'bg-danger-soft text-danger-ink',
  stone: 'bg-stone-soft text-stone-ink',
} as const

function Outcome({
  icon: Icon,
  tone,
  title,
  description,
  children,
}: {
  icon: typeof CircleCheck
  tone: keyof typeof TONES
  title: string
  description: ReactNode
  children?: ReactNode
}) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="animate-pop-in grid justify-items-center gap-3 px-6 py-8 text-center">
      <span className={cn('grid size-14 place-items-center rounded-full', TONES[tone])}>
        <Icon aria-hidden className="size-7" />
      </span>
      <h2 id={id} className="text-xl font-bold">
        {title}
      </h2>
      <div className="max-w-sm text-sm text-muted">{description}</div>
      {children && <div className="mt-2 grid w-full gap-2">{children}</div>}
    </section>
  )
}

function Result({ intent, hotel, onRetry }: { intent: SimIntent; hotel: string; onRetry: () => void }) {
  const { t } = useTranslation('finance')
  const back = useCallback(() => leavePage(intent.return_url), [intent.return_url])
  const approved = intent.status === 'approved'
  const secondsLeft = useCountdown(approved && Boolean(intent.return_url), RETURN_SECONDS, back)
  const methodKey = intent.method ? `methods.${intent.method}` : null
  const backButton = intent.return_url ? (
    <Button variant={approved ? 'primary' : 'secondary'} size="lg" className="w-full" onClick={back}>
      {t('sim.back', { hotel })}
    </Button>
  ) : null

  if (approved) {
    return (
      <Outcome
        icon={CircleCheck}
        tone="success"
        title={t('sim.approved')}
        description={
          <>
            <p>{t('sim.approvedText', { amount: moneyLabel(intent.amount, intent.currency), hotel })}</p>
            {methodKey && <p className="mt-2 font-semibold text-fg">{t(methodKey)}</p>}
          </>
        }
      >
        {backButton}
        <p className="text-xs text-muted">{intent.return_url ? t('sim.returning', { count: secondsLeft }) : t('sim.closeTab')}</p>
      </Outcome>
    )
  }
  if (intent.status === 'declined') {
    return (
      <Outcome icon={CircleX} tone="danger" title={t('sim.declined')} description={t('sim.declinedText')}>
        <Button variant="primary" size="lg" className="w-full" onClick={onRetry}>
          {t('sim.retry')}
        </Button>
        {backButton}
      </Outcome>
    )
  }
  return (
    <Outcome icon={Clock3} tone="stone" title={t('sim.expired')} description={t('sim.expiredText', { hotel })}>
      {backButton}
    </Outcome>
  )
}

/** Seconds left before `onDone` runs once (only while `active`). */
function useCountdown(active: boolean, seconds: number, onDone: () => void): number {
  const [left, setLeft] = useState(seconds)
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => setLeft((value) => Math.max(0, value - 1)), 1000)
    return () => window.clearInterval(id)
  }, [active])
  useEffect(() => {
    if (active && left === 0) onDone()
  }, [active, left, onDone])
  return left
}
