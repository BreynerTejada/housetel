import { AlertTriangle, ArrowLeft, ArrowRight, Check, CloudDownload, KeyRound, TriangleAlert } from 'lucide-react'
import { useId, useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { formatMoney, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  createConnection,
  updateConnection,
  useChannelCatalog,
  useChannelsMutation,
  type ChannelCode,
  type ChannelOptions,
  type Connection,
  type ConnectionInput,
  type IntegrationMode,
} from '../api'
import {
  buildConnectionInput,
  channelPrice,
  initialDraft,
  isValidMarkup,
  mappingProblems,
  planSellsOn,
  type ConnectionDraft,
  type RateDraft,
  type RoomDraft,
} from '../lib/channels'
import { tr } from '../lib/text'
import { ChannelMark } from './ChannelMark'

type Step = 'channel' | 'setup' | 'mapping' | 'review'

const CHANNEL_ORDER: ChannelCode[] = ['booksim', 'airsim', 'ical', 'channex']

export interface ConnectionWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  options: ChannelOptions
  /** Channel chosen before opening (skips the first step). */
  channel: ChannelCode | null
  /** Connection whose setup and mapping are being changed. */
  editing: Connection | null
}

/**
 * Connect a channel in four steps: which channel, how (name, mode, credentials), what it sells (categories and
 * rate plans with their markup) and a last look before connecting (with the first full sync). Editing reuses
 * the last three. Mount it with a new `key` every time it opens: it starts from its props.
 */
export function ConnectionWizard({ open, onOpenChange, options, channel, editing }: ConnectionWizardProps) {
  const { t } = useTranslation('channels')
  const startChannel = editing?.channel_code ?? channel
  const [draft, setDraft] = useState<ConnectionDraft | null>(() =>
    startChannel ? initialDraft(startChannel, options, editing ?? undefined) : null,
  )
  const [step, setStep] = useState<Step>(editing ? 'mapping' : startChannel ? 'setup' : 'channel')
  const [showProblems, setShowProblems] = useState(false)

  const steps: Step[] = editing ? ['setup', 'mapping', 'review'] : ['channel', 'setup', 'mapping', 'review']
  const index = steps.indexOf(step)

  const save = useChannelsMutation(
    (input: ConnectionInput) => (editing ? updateConnection(editing.id, input) : createConnection(input)),
    {
      onSuccess: (result) => {
        const failed = result.sync && (result.sync.failed || result.sync.retrying)
        if (failed) toast.warning(t('wizard.savedSyncFailed', { channel: result.name }))
        else if (editing) toast.success(t('wizard.updated', { channel: result.name }))
        else toast.success(result.sync ? t('wizard.connectedSynced', { channel: result.name }) : t('wizard.connected', { channel: result.name }))
        onOpenChange(false)
      },
    },
  )

  const integration = draft ? integrationOf(draft.channel, options, editing) : null
  const effectiveMode: IntegrationMode | null = integration ? (draft?.mode ?? integration.mode) : null
  const setupProblems = draft ? setupIssues(draft, effectiveMode, integration?.secrets ?? []) : []
  const problems = draft ? mappingProblems(draft) : []

  function pickChannel(code: ChannelCode) {
    setDraft(initialDraft(code, options))
    setShowProblems(false)
    setStep('setup')
  }

  function next() {
    if (step === 'setup' && setupProblems.length) return setShowProblems(true)
    if (step === 'mapping' && problems.length) return setShowProblems(true)
    setShowProblems(false)
    setStep(steps[Math.min(index + 1, steps.length - 1)])
  }

  function back() {
    setShowProblems(false)
    save.reset()
    setStep(steps[Math.max(index - 1, 0)])
  }

  function submit() {
    if (!draft) return
    save.mutate(buildConnectionInput(draft, { editing: Boolean(editing) }))
  }

  const title = editing ? t('wizard.editTitle', { channel: editing.name }) : t('wizard.title')

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[min(46rem,100vw)]">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>{t(`wizard.steps.${step}.hint`)}</SheetDescription>
          <Stepper steps={steps} current={index} onGo={(target) => target < index && setStep(steps[target])} />
        </SheetHeader>

        <SheetBody className="grid content-start gap-6">
          {step === 'channel' && <ChannelStep options={options} onPick={pickChannel} />}
          {step === 'setup' && draft && (
            <SetupStep
              draft={draft}
              options={options}
              mode={effectiveMode}
              storedSecrets={integration?.secrets ?? []}
              onChange={(patch) => setDraft((current) => current && { ...current, ...patch })}
            />
          )}
          {step === 'mapping' && draft && (
            <MappingStep
              draft={draft}
              options={options}
              mode={effectiveMode}
              onChange={(patch) => setDraft((current) => current && { ...current, ...patch })}
            />
          )}
          {step === 'review' && draft && <ReviewStep draft={draft} options={options} mode={effectiveMode} onChange={(patch) => setDraft((current) => current && { ...current, ...patch })} />}

          {showProblems && (step === 'setup' ? setupProblems : problems).length > 0 && (
            <ul role="alert" className="grid gap-1 rounded-lg bg-warning-soft px-4 py-3 text-[13px] text-warning-ink">
              {(step === 'setup' ? setupProblems : problems).map((problem) => (
                <li key={problem} className="flex gap-2">
                  <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                  {t(`wizard.problems.${problem}`)}
                </li>
              ))}
            </ul>
          )}
          {save.isError && <SaveError error={save.error} />}
        </SheetBody>

        <SheetFooter className="justify-between sm:justify-between">
          {index > 0 ? (
            <Button variant="ghost" onClick={back} disabled={save.isPending}>
              <ArrowLeft aria-hidden /> {t('wizard.back')}
            </Button>
          ) : (
            <span />
          )}
          {step === 'review' ? (
            <Button variant="primary" onClick={submit} loading={save.isPending}>
              <Check aria-hidden /> {editing ? t('wizard.save') : t('wizard.connect', { channel: draft?.name || '' })}
            </Button>
          ) : step !== 'channel' ? (
            <Button variant="primary" onClick={next}>
              {t('wizard.next')} <ArrowRight aria-hidden />
            </Button>
          ) : null}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

function integrationOf(channel: ChannelCode, options: ChannelOptions, editing: Connection | null) {
  if (channel !== 'ical' && channel !== 'channex') return null
  const kind = channel === 'ical' ? 'channel_ical' : 'channel_channex'
  return editing?.integration ?? options.integrations[kind] ?? null
}

function setupIssues(draft: ConnectionDraft, mode: IntegrationMode | null, storedSecrets: string[]): string[] {
  const issues: string[] = []
  if (!draft.name.trim()) issues.push('name')
  if (draft.channel === 'channex' && mode === 'real') {
    if (!draft.config.environment) issues.push('environment')
    if (!draft.config.property_id?.trim()) issues.push('propertyId')
    if (!draft.secrets.api_key?.trim() && !storedSecrets.includes('api_key')) issues.push('apiKey')
  }
  return issues
}

// ---- steps ------------------------------------------------------------------------------------------------------

function Stepper({ steps, current, onGo }: { steps: Step[]; current: number; onGo: (index: number) => void }) {
  const { t } = useTranslation('channels')
  return (
    <ol className="mt-3 flex flex-wrap items-center gap-x-1 gap-y-2" aria-label={t('wizard.progress')}>
      {steps.map((item, index) => {
        const done = index < current
        const active = index === current
        return (
          <li key={item} className="flex items-center gap-1">
            {index > 0 && <span aria-hidden className={cn('h-px w-4 sm:w-6', done || active ? 'bg-accent' : 'bg-border-strong')} />}
            <button
              type="button"
              onClick={() => onGo(index)}
              disabled={!done}
              aria-current={active ? 'step' : undefined}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                active && 'bg-accent-soft text-accent-ink',
                done && 'text-fg hover:bg-surface-2',
                !done && !active && 'text-subtle',
              )}
            >
              <span
                aria-hidden
                className={cn(
                  'grid size-4 place-items-center rounded-full text-[10px] leading-none',
                  active ? 'bg-accent text-on-accent' : done ? 'bg-success text-on-accent' : 'border border-border-strong',
                )}
              >
                {done ? <Check className="size-2.5" strokeWidth={3} /> : index + 1}
              </span>
              {t(`wizard.steps.${item}.label`)}
            </button>
          </li>
        )
      })}
    </ol>
  )
}

function ChannelStep({ options, onPick }: { options: ChannelOptions; onPick: (code: ChannelCode) => void }) {
  const { t } = useTranslation('channels')
  const byCode = new Map(options.channels.map((item) => [item.code, item]))
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {CHANNEL_ORDER.map((code) => {
        const option = byCode.get(code)
        const taken = Boolean(option?.connected && !option.multiple)
        return (
          <button
            key={code}
            type="button"
            disabled={taken}
            onClick={() => onPick(code)}
            className={cn(
              'group grid content-start gap-3 rounded-xl border border-border bg-surface p-4 text-left shadow-xs transition-[border-color,box-shadow]',
              'hover:border-accent hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
              'disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:border-border disabled:hover:shadow-xs',
            )}
          >
            <span className="flex items-start justify-between gap-3">
              <ChannelMark channel={code} size="lg" />
              <Badge tone={taken ? 'success' : 'neutral'}>{taken ? t('wizard.alreadyConnected') : t(`channels.${code}.tag`)}</Badge>
            </span>
            <span>
              <span className="block text-[15px] font-bold tracking-[-0.01em] text-fg">{t(`channels.${code}.name`)}</span>
              <span className="mt-1 block text-[13px] leading-5 text-muted">{t(`channels.${code}.description`)}</span>
            </span>
          </button>
        )
      })}
    </div>
  )
}

function Field({ label, htmlFor, hint, children }: { label: ReactNode; htmlFor?: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  )
}

function SetupStep({
  draft,
  options,
  mode,
  storedSecrets,
  onChange,
}: {
  draft: ConnectionDraft
  options: ChannelOptions
  mode: IntegrationMode | null
  storedSecrets: string[]
  onChange: (patch: Partial<ConnectionDraft>) => void
}) {
  const { t, i18n } = useTranslation('channels')
  const lang = normalizeLang(i18n.language)
  const nameId = useId()
  const hasIntegration = draft.channel === 'ical' || draft.channel === 'channex'
  const fields = draft.channel === 'channex' ? (options.integrations.channel_channex?.fields ?? []) : []

  return (
    <>
      <div className="flex items-center gap-3 rounded-lg bg-surface-2/70 px-4 py-3">
        <ChannelMark channel={draft.channel} />
        <div className="min-w-0">
          <p className="text-sm font-bold text-fg">{t(`channels.${draft.channel}.name`)}</p>
          <p className="text-xs text-muted">{t(`channels.${draft.channel}.short`)}</p>
        </div>
      </div>

      <Field label={t('wizard.name')} htmlFor={nameId} hint={t(`wizard.nameHint.${draft.channel}`)}>
        <Input id={nameId} value={draft.name} maxLength={120} onChange={(event) => onChange({ name: event.target.value })} />
      </Field>

      {hasIntegration && mode && (
        <fieldset className="grid gap-2">
          <legend className="mb-1.5 text-[13px] font-semibold text-fg">{t('wizard.mode')}</legend>
          <RadioGroup value={mode} onValueChange={(value) => onChange({ mode: value as IntegrationMode })} className="gap-2 sm:grid-cols-2">
            {(['simulated', 'real'] as const).map((value) => (
              <label
                key={value}
                className={cn(
                  'flex cursor-pointer gap-3 rounded-lg border border-border p-3 transition-colors hover:border-border-strong',
                  mode === value && 'border-accent bg-accent-soft/40',
                )}
              >
                <RadioGroupItem value={value} className="mt-0.5" />
                <span className="grid gap-0.5">
                  <span className="text-[13px] font-semibold text-fg">{t(`mode.${value}`)}</span>
                  <span className="text-xs leading-4 text-muted">{t(`wizard.modeHint.${draft.channel}.${value}`)}</span>
                </span>
              </label>
            ))}
          </RadioGroup>
          <p className="text-xs text-muted">{t('wizard.modeShared')}</p>
        </fieldset>
      )}

      {draft.channel === 'channex' && mode === 'real' && (
        <section className="grid gap-4 rounded-xl border border-border p-4" aria-labelledby={`${nameId}-cx`}>
          <h3 id={`${nameId}-cx`} className="flex items-center gap-2 text-[13px] font-bold text-fg">
            <KeyRound aria-hidden className="size-4 text-muted" /> {t('wizard.credentials')}
          </h3>
          {fields.map((field) => {
            const label = lang === 'en' ? field.label_en : field.label_es
            const help = lang === 'en' ? field.help_en : field.help_es
            const id = `${nameId}-${field.name}`
            if (field.secret) {
              const stored = storedSecrets.includes(field.name)
              return (
                <Field key={field.name} label={label} htmlFor={id} hint={stored ? t('wizard.secretStored') : help}>
                  <Input
                    id={id}
                    type="password"
                    autoComplete="off"
                    value={draft.secrets[field.name] ?? ''}
                    placeholder={stored ? '••••••••' : ''}
                    onChange={(event) => onChange({ secrets: { ...draft.secrets, [field.name]: event.target.value } })}
                  />
                </Field>
              )
            }
            if (field.type === 'select') {
              return (
                <Field key={field.name} label={label} htmlFor={id} hint={help}>
                  <Select value={draft.config[field.name] ?? ''} onValueChange={(value) => onChange({ config: { ...draft.config, [field.name]: value } })}>
                    <SelectTrigger id={id}>
                      <SelectValue placeholder={t('wizard.choose')} />
                    </SelectTrigger>
                    <SelectContent>
                      {(field.options ?? []).map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {lang === 'en' ? option.label_en : option.label_es}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
              )
            }
            return (
              <Field key={field.name} label={label} htmlFor={id} hint={help}>
                <Input
                  id={id}
                  value={draft.config[field.name] ?? ''}
                  onChange={(event) => onChange({ config: { ...draft.config, [field.name]: event.target.value } })}
                />
              </Field>
            )
          })}
        </section>
      )}

      {draft.channel === 'ical' && (
        <label className="flex items-start gap-3 rounded-lg border border-border p-3">
          <Switch checked={draft.importAll} onCheckedChange={(checked) => onChange({ importAll: checked })} className="mt-0.5" />
          <span className="grid gap-0.5">
            <span className="text-[13px] font-semibold text-fg">{t('wizard.importAll')}</span>
            <span className="text-xs leading-4 text-muted">{t('wizard.importAllHint')}</span>
          </span>
        </label>
      )}

      {(draft.channel === 'booksim' || draft.channel === 'airsim') && (
        <p className="rounded-lg bg-info-soft px-4 py-3 text-[13px] leading-5 text-info-ink">{t('wizard.simulatedNote')}</p>
      )}
    </>
  )
}

function MappingStep({
  draft,
  options,
  mode,
  onChange,
}: {
  draft: ConnectionDraft
  options: ChannelOptions
  mode: IntegrationMode | null
  onChange: (patch: Partial<ConnectionDraft>) => void
}) {
  const { t, i18n } = useTranslation('channels')
  const lang = normalizeLang(i18n.language)
  const listId = useId()
  const ical = draft.channel === 'ical'
  const realChannex = draft.channel === 'channex' && mode === 'real'
  const [wantCatalog, setWantCatalog] = useState(false)
  const catalog = useChannelCatalog('channex', realChannex && wantCatalog)

  const roomTypes = useMemo(() => new Map(options.room_types.map((roomType) => [roomType.id, roomType])), [options.room_types])
  const plans = useMemo(() => new Map(options.rate_plans.map((plan) => [plan.id, plan])), [options.rate_plans])
  const enabledTypes = new Set(draft.rooms.filter((room) => room.enabled && !room.roomId).map((room) => room.roomTypeId))

  function setRoom(index: number, patch: Partial<RoomDraft>) {
    onChange({ rooms: draft.rooms.map((room, i) => (i === index ? { ...room, ...patch } : room)) })
  }
  function setRate(index: number, patch: Partial<RateDraft>) {
    onChange({ rates: draft.rates.map((rate, i) => (i === index ? { ...rate, ...patch } : rate)) })
  }

  const visibleRates = draft.rates
    .map((rate, index) => ({ rate, index }))
    .filter(({ rate }) => !rate.roomTypeId || enabledTypes.has(rate.roomTypeId))

  return (
    <>
      {realChannex && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-border-strong px-4 py-3">
          <p className="min-w-0 flex-1 text-[13px] text-muted">{t('wizard.catalogHint')}</p>
          <Button size="sm" onClick={() => (wantCatalog ? void catalog.refetch() : setWantCatalog(true))} loading={catalog.isFetching}>
            <CloudDownload aria-hidden /> {t('wizard.loadCatalog')}
          </Button>
          {catalog.isError && <p className="w-full text-xs text-danger-ink">{errorMessage(catalog.error, t)}</p>}
          {catalog.data && (
            <p className="w-full text-xs text-success-ink">
              {t('wizard.catalogLoaded', { rooms: catalog.data.rooms.length, rates: catalog.data.rates.length })}
            </p>
          )}
        </div>
      )}
      {catalog.data && (
        <>
          <datalist id={`${listId}-rooms`}>
            {catalog.data.rooms.map((room) => (
              <option key={room.id} value={room.id}>
                {room.title}
              </option>
            ))}
          </datalist>
          <datalist id={`${listId}-rates`}>
            {catalog.data.rates.map((rate) => (
              <option key={rate.id} value={rate.id}>
                {rate.title}
              </option>
            ))}
          </datalist>
        </>
      )}

      <section className="grid gap-3" aria-labelledby={`${listId}-rooms-title`}>
        <header>
          <h3 id={`${listId}-rooms-title`} className="text-sm font-bold text-fg">
            {ical ? t('wizard.calendars') : t('wizard.rooms')}
          </h3>
          <p className="text-xs text-muted">{ical ? t('wizard.calendarsHint') : t('wizard.roomsHint')}</p>
        </header>
        <ul className="grid gap-2">
          {draft.rooms.map((room, index) => {
            const roomType = roomTypes.get(room.roomTypeId)
            const roomNumber = room.roomId ? roomType?.rooms.find((item) => item.id === room.roomId)?.number : null
            const label = roomNumber ? t('card.room', { number: roomNumber }) : tr(roomType?.name, lang) || roomType?.code
            const checkId = `${listId}-room-${index}`
            return (
              <li
                key={`${room.roomTypeId}:${room.roomId ?? ''}:${room.id ?? index}`}
                className={cn(
                  'grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,15rem)] sm:items-center',
                  !room.enabled && 'bg-surface-2/50',
                )}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <Checkbox id={checkId} checked={room.enabled} onCheckedChange={(checked) => setRoom(index, { enabled: checked === true })} />
                  <span aria-hidden className="h-7 w-1 shrink-0 rounded-full" style={{ background: roomType?.color }} />
                  <label htmlFor={checkId} className="min-w-0 cursor-pointer">
                    <span className="block truncate text-[13px] font-semibold text-fg">{label}</span>
                    <span className="block text-2xs font-semibold tracking-wide text-muted">
                      {roomType?.code}
                      {roomType?.kind === 'dorm' && ` · ${t('wizard.dorm')}`}
                    </span>
                  </label>
                </div>
                {ical ? (
                  <Input
                    type="url"
                    inputMode="url"
                    value={room.importUrl}
                    disabled={!room.enabled}
                    placeholder={t('wizard.importUrlPlaceholder')}
                    aria-label={t('wizard.importUrlFor', { room: label })}
                    onChange={(event) => setRoom(index, { importUrl: event.target.value })}
                  />
                ) : (
                  <Input
                    value={room.externalId}
                    disabled={!room.enabled}
                    list={catalog.data ? `${listId}-rooms` : undefined}
                    aria-label={t('wizard.roomCodeFor', { room: label })}
                    placeholder={t('wizard.roomCode')}
                    className="num"
                    onChange={(event) => setRoom(index, { externalId: event.target.value })}
                  />
                )}
              </li>
            )
          })}
        </ul>
      </section>

      {!ical && (
        <section className="grid gap-3" aria-labelledby={`${listId}-rates-title`}>
          <header>
            <h3 id={`${listId}-rates-title`} className="text-sm font-bold text-fg">
              {t('wizard.rates')}
            </h3>
            <p className="text-xs text-muted">{t('wizard.ratesHint')}</p>
          </header>
          {visibleRates.length === 0 ? (
            <p className="rounded-lg bg-surface-2 px-4 py-3 text-[13px] text-muted">{t('wizard.noRates')}</p>
          ) : (
            <ul className="grid gap-2">
              {visibleRates.map(({ rate, index }) => {
                const plan = plans.get(rate.planId)
                if (!plan) return null
                const roomType = rate.roomTypeId ? roomTypes.get(rate.roomTypeId) : null
                const closed = !planSellsOn(plan, draft.channel)
                const checkId = `${listId}-rate-${index}`
                const markupOk = isValidMarkup(rate.markup)
                const sample = rate.roomTypeId
                  ? plan.samples?.find((item) => item.room_type === rate.roomTypeId)
                  : (plan.samples?.find((item) => enabledTypes.has(item.room_type)) ?? plan.samples?.[0])
                const preview = sample && markupOk ? channelPrice(sample.price, rate.markup.replace(',', '.') || '0', options.currency) : null
                const planName = tr(plan.name, lang) || plan.code
                return (
                  <li key={`${rate.planId}:${rate.roomTypeId ?? ''}`} className={cn('grid gap-3 rounded-lg border border-border p-3', !rate.enabled && 'bg-surface-2/50')}>
                    <div className="flex min-w-0 items-start gap-3">
                      <Checkbox
                        id={checkId}
                        className="mt-0.5"
                        checked={rate.enabled}
                        onCheckedChange={(checked) => setRate(index, { enabled: checked === true })}
                      />
                      <label htmlFor={checkId} className="min-w-0 flex-1 cursor-pointer">
                        <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] font-semibold text-fg">
                          {planName}
                          <Badge tone="neutral">{t(`wizard.planKind.${plan.kind}`)}</Badge>
                          {roomType && <span className="text-2xs font-semibold tracking-wide text-muted">{roomType.code}</span>}
                        </span>
                        <span className="block text-2xs font-semibold tracking-wide text-muted">{plan.code}</span>
                      </label>
                    </div>
                    <div className="grid grid-cols-[minmax(0,1fr)_6.5rem] gap-2 sm:grid-cols-[minmax(0,1fr)_7rem_minmax(0,13rem)] sm:items-center">
                      <Input
                        value={rate.externalId}
                        disabled={!rate.enabled}
                        list={catalog.data ? `${listId}-rates` : undefined}
                        aria-label={t('wizard.rateCodeFor', { plan: planName })}
                        placeholder={t('wizard.rateCode')}
                        className="num"
                        onChange={(event) => setRate(index, { externalId: event.target.value })}
                      />
                      <div className="relative">
                        <Input
                          value={rate.markup}
                          disabled={!rate.enabled}
                          inputMode="decimal"
                          aria-label={t('wizard.markupFor', { plan: planName })}
                          aria-invalid={!markupOk || undefined}
                          className="num pr-7 text-right"
                          onChange={(event) => setRate(index, { markup: event.target.value })}
                        />
                        <span aria-hidden className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-xs text-muted">
                          %
                        </span>
                      </div>
                      <p className="col-span-2 text-xs text-muted sm:col-span-1">
                        {preview && sample ? (
                          <>
                            {t('wizard.pricePreview', { code: sample.room_type_code, price: formatMoney(sample.price, options.currency) })}{' '}
                            <span className="num font-semibold text-fg">{formatMoney(preview, options.currency)}</span>
                          </>
                        ) : (
                          t('wizard.noPreview')
                        )}
                      </p>
                    </div>
                    {closed && rate.enabled && (
                      <p className="flex items-start gap-1.5 text-xs text-warning-ink">
                        <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                        {!plan.is_active ? t('wizard.planInactive') : !plan.is_public ? t('wizard.planNotPublic') : t('wizard.planNotOnChannel', { channel: draft.name })}
                      </p>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      )}
    </>
  )
}

function ReviewStep({
  draft,
  options,
  mode,
  onChange,
}: {
  draft: ConnectionDraft
  options: ChannelOptions
  mode: IntegrationMode | null
  onChange: (patch: Partial<ConnectionDraft>) => void
}) {
  const { t, i18n } = useTranslation('channels')
  const lang = normalizeLang(i18n.language)
  const roomTypes = new Map(options.room_types.map((roomType) => [roomType.id, roomType]))
  const plans = new Map(options.rate_plans.map((plan) => [plan.id, plan]))
  const rooms = draft.rooms.filter((room) => room.enabled)
  const rates = draft.rates.filter((rate) => rate.enabled && (!rate.roomTypeId || rooms.some((room) => room.roomTypeId === rate.roomTypeId)))
  const imports = rooms.filter((room) => room.importUrl.trim()).length
  const pushes = draft.channel !== 'ical'

  return (
    <>
      <dl className="grid gap-x-6 gap-y-3 rounded-xl border border-border p-4 text-[13px] sm:grid-cols-[10rem_minmax(0,1fr)]">
        <dt className="text-muted">{t('wizard.review.channel')}</dt>
        <dd className="flex items-center gap-2 font-semibold text-fg">
          <ChannelMark channel={draft.channel} size="sm" /> {t(`channels.${draft.channel}.name`)}
        </dd>
        <dt className="text-muted">{t('wizard.name')}</dt>
        <dd className="font-semibold text-fg">{draft.name}</dd>
        {mode && (
          <>
            <dt className="text-muted">{t('wizard.mode')}</dt>
            <dd className="font-semibold text-fg">{t(`mode.${mode}`)}</dd>
          </>
        )}
        <dt className="text-muted">{draft.channel === 'ical' ? t('wizard.calendars') : t('wizard.rooms')}</dt>
        <dd className="grid gap-1">
          {rooms.map((room) => {
            const roomType = roomTypes.get(room.roomTypeId)
            const number = room.roomId ? roomType?.rooms.find((item) => item.id === room.roomId)?.number : null
            return (
              <span key={`${room.roomTypeId}:${room.roomId ?? ''}`} className="flex flex-wrap items-center gap-x-2 text-fg">
                <span className="font-semibold">{number ? t('card.room', { number }) : tr(roomType?.name, lang)}</span>
                {room.externalId && <span className="num text-xs text-muted">↔ {room.externalId}</span>}
                {room.importUrl && <span className="text-xs text-muted">· {t('wizard.review.imports')}</span>}
              </span>
            )
          })}
        </dd>
        {draft.channel !== 'ical' && (
          <>
            <dt className="text-muted">{t('wizard.rates')}</dt>
            <dd className="grid gap-1">
              {rates.length === 0 && <span className="text-muted">{t('wizard.review.noRates')}</span>}
              {rates.map((rate) => {
                const plan = plans.get(rate.planId)
                const roomType = rate.roomTypeId ? roomTypes.get(rate.roomTypeId) : null
                return (
                  <span key={`${rate.planId}:${rate.roomTypeId ?? ''}`} className="flex flex-wrap items-center gap-x-2 text-fg">
                    <span className="font-semibold">{tr(plan?.name, lang) || plan?.code}</span>
                    {roomType && <span className="text-xs text-muted">{roomType.code}</span>}
                    <span className="num text-xs text-muted">↔ {rate.externalId}</span>
                    <Badge tone={Number(rate.markup.replace(',', '.') || 0) > 0 ? 'accent' : 'neutral'}>
                      {t('wizard.review.markup', { value: rate.markup.trim() || '0' })}
                    </Badge>
                  </span>
                )
              })}
            </dd>
          </>
        )}
      </dl>

      {draft.channel === 'ical' && (
        <p className="rounded-lg bg-info-soft px-4 py-3 text-[13px] leading-5 text-info-ink">
          {t('wizard.review.icalNote', { count: imports })}
        </p>
      )}

      {pushes && (
        <label className="flex items-start gap-3 rounded-lg border border-border p-3">
          <Checkbox checked={draft.fullSync} onCheckedChange={(checked) => onChange({ fullSync: checked === true })} className="mt-0.5" />
          <span className="grid gap-0.5">
            <span className="text-[13px] font-semibold text-fg">{t('wizard.fullSync')}</span>
            <span className="text-xs leading-4 text-muted">{t('wizard.fullSyncHint')}</span>
          </span>
        </label>
      )}
    </>
  )
}

function SaveError({ error }: { error: unknown }) {
  const { t } = useTranslation('channels')
  const fields = isApiError(error) && error.fields ? Object.values(error.fields).flat() : []
  return (
    <div role="alert" className="grid gap-1.5 rounded-lg bg-danger-soft px-4 py-3 text-[13px] text-danger-ink">
      <p className="flex items-start gap-2 font-semibold">
        <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
        {errorMessage(error, t)}
      </p>
      {fields.length > 1 && (
        <ul className="grid list-disc gap-0.5 pl-10">
          {fields.map((message, index) => (
            <li key={index}>{String(message)}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
