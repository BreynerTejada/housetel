import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, Sparkles } from 'lucide-react'
import { useCallback, useId, useState, type Dispatch, type FormEvent, type SetStateAction } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { applyOnboarding, proposeOnboarding, type OnboardingSummary, type Proposal, type ProposalResponse } from '../api'
import { KeyTags } from '../components/onboarding/KeyTags'
import { ReviewStep } from '../components/onboarding/ReviewStep'

type Step = 'describe' | 'review' | 'done'
const STEPS: Step[] = ['describe', 'review', 'done']

/** `/app/onboarding`: describe the hotel → review the AI's proposal → everything created with the contract
 * services (room types, rooms, rate plans, extras and the profile). */
export default function OnboardingPage() {
  const { t } = useTranslation('ai')
  const queryClient = useQueryClient()
  const [step, setStep] = useState<Step>('describe')
  const [description, setDescription] = useState('')
  const [website, setWebsite] = useState('')
  const [response, setResponse] = useState<ProposalResponse | null>(null)
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [summary, setSummary] = useState<OnboardingSummary | null>(null)
  const updateProposal = useCallback<Dispatch<SetStateAction<Proposal>>>(
    (value) => setProposal((current) => (current === null ? current : typeof value === 'function' ? value(current) : value)),
    [],
  )

  const propose = useMutation({
    mutationFn: () => proposeOnboarding({ description: description.trim(), website_url: website.trim() }),
    onSuccess: (result) => {
      setResponse(result)
      setProposal(result.proposal)
      setStep('review')
      window.scrollTo({ top: 0 })
    },
  })
  const apply = useMutation({
    mutationFn: (value: Proposal) => applyOnboarding(value),
    onSuccess: (result) => {
      setSummary(result)
      setStep('done')
      window.scrollTo({ top: 0 })
      // Room types, rooms, plans, the grid and the profile changed: let every page refetch.
      void queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] !== 'me' })
    },
  })

  function restart() {
    setStep('describe')
    setResponse(null)
    setProposal(null)
    setSummary(null)
    propose.reset()
    apply.reset()
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader title={t('onboarding.title')} description={t('onboarding.description')} />
      <Stepper step={step} />
      {step === 'describe' && (
        <DescribeStep
          description={description}
          website={website}
          onDescription={setDescription}
          onWebsite={setWebsite}
          pending={propose.isPending}
          error={propose.isError ? errorMessage(propose.error, t) : null}
          onSubmit={() => propose.mutate()}
        />
      )}
      {step === 'review' && proposal && response && (
        <ReviewStep
          proposal={proposal}
          setProposal={updateProposal}
          response={response}
          onBack={() => {
            apply.reset()
            setStep('describe')
          }}
          onApply={() => apply.mutate(proposal)}
          applying={apply.isPending}
          applyError={apply.isError ? withFieldDetails(errorMessage(apply.error, t), apply.error) : null}
        />
      )}
      {step === 'done' && summary && <DoneStep summary={summary} onRestart={restart} />}
    </div>
  )
}

/** The error's message plus the field messages that say something more (e.g. which room numbers clash). */
function withFieldDetails(message: string, error: unknown): string {
  if (isApiError(error) && error.fields) {
    const details = Object.values(error.fields).flat().filter((item) => item && item !== message)
    if (details.length) return `${message} ${details.join(' ')}`
  }
  return message
}

/** The three moments of the flow, in order (the order is real: nothing is created before the review). */
function Stepper({ step }: { step: Step }) {
  const { t } = useTranslation('ai')
  const current = STEPS.indexOf(step)
  return (
    <ol aria-label={t('onboarding.stepsLabel')} className="mb-6 flex flex-wrap items-center gap-x-2 gap-y-2 text-[13px]">
      {STEPS.map((item, index) => {
        const done = index < current || step === 'done'
        const active = index === current
        return (
          <li key={item} aria-current={active ? 'step' : undefined} className="flex items-center gap-2">
            <span
              className={cn(
                'num grid size-6 place-items-center rounded-full border text-[11px] font-bold',
                done && 'border-success bg-success-soft text-success-ink',
                active && !done && 'border-accent bg-accent text-on-accent',
                !done && !active && 'border-border-strong text-muted',
              )}
            >
              {done ? <Check aria-hidden className="size-3.5" /> : index + 1}
            </span>
            <span className={cn('font-semibold', active ? 'text-fg' : 'text-muted')}>{t(`onboarding.step_${item}`)}</span>
            {index < STEPS.length - 1 && <span aria-hidden className="mx-1 h-px w-6 bg-border-strong sm:w-12" />}
          </li>
        )
      })}
    </ol>
  )
}

function DescribeStep({
  description,
  website,
  onDescription,
  onWebsite,
  pending,
  error,
  onSubmit,
}: {
  description: string
  website: string
  onDescription: (value: string) => void
  onWebsite: (value: string) => void
  pending: boolean
  error: string | null
  onSubmit: () => void
}) {
  const { t, i18n } = useTranslation('ai')
  const lang = normalizeLang(i18n.language)
  const descriptionId = useId()
  const websiteId = useId()
  const hintId = useId()
  const [missing, setMissing] = useState(false)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!description.trim() && !website.trim()) {
      setMissing(true)
      return
    }
    setMissing(false)
    onSubmit()
  }

  return (
    <Card className="max-w-3xl">
      <CardContent className="py-6">
        <form onSubmit={submit} className="grid gap-5" noValidate>
          <div className="grid gap-1.5">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <Label htmlFor={descriptionId} className="text-sm">
                {t('onboarding.describeLabel')}
              </Label>
              <Button type="button" variant="link" size="sm" className="h-auto px-0" disabled={pending} onClick={() => onDescription(t('onboarding.example'))}>
                {t('onboarding.useExample')}
              </Button>
            </div>
            <Textarea
              id={descriptionId}
              name="description"
              rows={7}
              maxLength={5000}
              value={description}
              disabled={pending}
              aria-describedby={hintId}
              aria-invalid={missing || undefined}
              placeholder={t('onboarding.describePlaceholder')}
              onChange={(event) => onDescription(event.target.value)}
              className="text-[14.5px]"
            />
            <p id={hintId} className="text-xs text-muted">
              {t('onboarding.describeHint')}
            </p>
          </div>
          <div className="grid gap-1.5 sm:max-w-md">
            <Label htmlFor={websiteId}>{t('onboarding.websiteLabel')}</Label>
            <Input
              id={websiteId}
              name="website"
              type="url"
              inputMode="url"
              autoComplete="url"
              value={website}
              disabled={pending}
              placeholder={t('onboarding.websitePlaceholder')}
              onChange={(event) => onWebsite(event.target.value)}
            />
          </div>
          {missing && (
            <p role="alert" className="text-[13px] text-danger-ink">
              {t('onboarding.needInput')}
            </p>
          )}
          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger-ink">
              {error}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant="primary" loading={pending}>
              <Sparkles aria-hidden />
              {t('onboarding.propose')}
            </Button>
            {pending && (
              <p role="status" className="text-[13px] text-muted">
                {t('onboarding.proposing')}
              </p>
            )}
          </div>
          <p className="text-xs text-subtle" lang={lang}>
            {t('onboarding.privacy')}
          </p>
        </form>
      </CardContent>
    </Card>
  )
}

const LINKS: { key: keyof OnboardingSummary['links']; label: string }[] = [
  { key: 'rates', label: 'onboarding.goRates' },
  { key: 'room_types', label: 'onboarding.goRoomTypes' },
  { key: 'rooms', label: 'onboarding.goRooms' },
  { key: 'property', label: 'onboarding.goProperty' },
]

/** Result: the rooms hang on the rack, stamped as created, with the way to each new part of the setup. */
function DoneStep({ summary, onRestart }: { summary: OnboardingSummary; onRestart: () => void }) {
  const { t, i18n } = useTranslation('ai')
  const lang = normalizeLang(i18n.language)
  return (
    <Card className="max-w-4xl overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border px-6 py-5">
        <div className="min-w-0">
          <h2 className="text-lg font-bold text-fg">{t('onboarding.doneTitle')}</h2>
          <p className="mt-1 text-sm text-muted">
            {t('onboarding.doneText', { types: summary.room_types.length, rooms: summary.rooms_created })}
          </p>
        </div>
        <span className="inline-flex -rotate-2 items-center rounded-sm border-2 border-success/70 px-2.5 py-1 text-xs font-extrabold tracking-[0.14em] text-success-ink uppercase motion-safe:animate-pop-in">
          {t('onboarding.created')}
        </span>
      </div>
      <div className="grid gap-5 px-6 py-5">
        <p className="eyebrow">{t('onboarding.doneKeys')}</p>
        <ul className="grid gap-4">
          {summary.room_types.map((item) => (
            <li key={item.id} className="grid gap-2">
              <p className="text-sm font-semibold text-fg">
                {item.name[lang] || item.name.es} <span className="num font-normal text-muted">· {item.code}</span>
              </p>
              <KeyTags hung rooms={item.rooms} label={t('onboarding.keyRackLabel', { name: item.name[lang] || item.name.es, rooms: item.rooms.join(', ') })} />
            </li>
          ))}
        </ul>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <p className="text-[13px] font-semibold text-fg">{t('onboarding.donePlans')}</p>
            <ul className="flex flex-wrap gap-1.5">
              {summary.rate_plans.map((code) => (
                <li key={code}>
                  <Badge tone={code === 'FLEX' ? 'accent' : 'neutral'}>{t(`onboarding.planName${code}`, { defaultValue: code })}</Badge>
                </li>
              ))}
            </ul>
          </div>
          {summary.extras.length > 0 && (
            <div className="grid gap-1.5">
              <p className="text-[13px] font-semibold text-fg">{t('onboarding.doneExtras')}</p>
              <ul className="flex flex-wrap gap-1.5">
                {summary.extras.map((code) => (
                  <li key={code}>
                    <Badge tone="neutral">{code}</Badge>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-border bg-surface-2/50 px-6 py-4">
        {LINKS.map(({ key, label }, index) => (
          <Button key={key} asChild size="sm" variant={index === 0 ? 'primary' : 'secondary'}>
            <Link to={summary.links[key]}>
              {t(label)}
              {index === 0 && <ArrowRight aria-hidden />}
            </Link>
          </Button>
        ))}
        <Button variant="ghost" size="sm" className="sm:ml-auto" onClick={onRestart}>
          {t('onboarding.again')}
        </Button>
      </div>
    </Card>
  )
}
