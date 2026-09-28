import { ArrowUpRight, BookOpenText, ChevronDown, Copy, FlaskConical, Info, LifeBuoy, SquareTerminal, TriangleAlert, Webhook, Zap } from 'lucide-react'
import { useId, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { normalizeLang } from '@/lib/format'
import { hasSupportChannel, mailtoLink, useRuntimeConfig, whatsappLink } from '@/lib/runtime'
import { cn } from '@/lib/utils'
import type { Integration } from '../api'
import { DOCS_PATH, guideFor, isLocalUrl, TUNNEL_COMMAND, webhookUrlFor, type GuideStep, type IntegrationGuide as Guide } from '../lib/guides'
import { KIND_META } from '../lib/integrations'

/** `environment` values of the providers' forms that mean "test" (Wompi/Factus sandbox, Channex staging). */
const TEST_ENVIRONMENTS = new Set(['sandbox', 'staging', 'test'])

async function copyText(text: string, done: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(done)
  } catch {
    // Clipboard blocked (insecure origin, permissions): show the text so it can be copied by hand.
    toast.message(text)
  }
}

interface Props {
  integration: Integration
  /** `environment` chosen in the form (highlights sandbox or production). */
  environment?: string | null
  /** Label of a CONFIG_FIELDS entry in the current language (the backend's, so both always match). */
  fieldLabel: (name: string) => string
  /** Open when it first renders (the card's "Guía" button, or an integration that is not live yet). */
  defaultOpen?: boolean
}

/**
 * The provider's step-by-step guide to real mode (plan P6), inside the integration sheet: the account to create
 * (official link), test vs live environment, the steps in order with the webhook URL where it belongs (built on
 * `public_base_url`, with the tunnel hint while it is a local address), where each value lives and the long guide.
 */
export function IntegrationGuide({ integration, environment, fieldLabel, defaultOpen = false }: Props) {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const guide = guideFor(integration.kind, lang)
  const titleId = useId()
  if (!guide) return null
  const steps = guide.steps
  const hasWebhookStep = steps.some((step) => step.webhook)
  const webhookPath = KIND_META[integration.kind]?.webhookPath

  return (
    <details
      open={defaultOpen}
      className="group/guide rounded-xl border border-border bg-surface shadow-xs [&[open]>summary]:border-b [&[open]>summary]:border-border"
    >
      <summary
        className={cn(
          'flex cursor-pointer list-none items-center gap-3 rounded-xl px-4 py-3 [&::-webkit-details-marker]:hidden',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
        )}
      >
        <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent-ink">
          <BookOpenText className="size-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span id={titleId} className="block text-sm font-bold text-fg">
            {t('integrations.guide.title', { provider: guide.provider })}
          </span>
          <span className="block text-xs text-muted">{t('integrations.guide.stepsCount', { count: steps.length })}</span>
        </span>
        <ChevronDown aria-hidden className="size-4 shrink-0 text-muted transition-transform group-open/guide:rotate-180" />
      </summary>

      <div className="grid grid-cols-1 gap-5 px-4 pt-4 pb-4">
        {guide.account && (
          <Button asChild size="sm" className="w-fit">
            <a href={guide.account.href} target="_blank" rel="noreferrer">
              {guide.account.label}
              <ArrowUpRight aria-hidden />
              <span className="sr-only">{t('integrations.guide.newTab')}</span>
            </a>
          </Button>
        )}

        {guide.environments ? <Environments guide={guide} environment={environment} /> : null}
        {guide.note && (
          <p className="flex gap-2 rounded-lg border border-info/25 bg-info-soft/70 px-3 py-2 text-[13px] text-info-ink">
            <Info aria-hidden className="mt-0.5 size-4 shrink-0" />
            {guide.note}
          </p>
        )}

        <ol aria-labelledby={titleId} className="grid grid-cols-1">
          {steps.map((step, index) => (
            <Step key={step.title} step={step} number={index + 1} last={index === steps.length - 1}>
              {step.webhook && webhookPath ? <WebhookBox kind={integration.kind} path={webhookPath} /> : null}
            </Step>
          ))}
        </ol>
        {!hasWebhookStep && webhookPath ? <WebhookBox kind={integration.kind} path={webhookPath} /> : null}

        {guide.keys.length > 0 && (
          <section aria-labelledby={`${titleId}-keys`} className="grid grid-cols-1 gap-2">
            <h4 id={`${titleId}-keys`} className="eyebrow">
              {t('integrations.guide.keysTitle')}
            </h4>
            <dl className="grid gap-px overflow-hidden rounded-lg border border-border bg-border">
              {guide.keys.map((key) => (
                <div key={key.field} className="grid gap-0.5 bg-surface px-3 py-2 sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)] sm:gap-3">
                  <dt className="text-[13px] font-semibold text-fg">{fieldLabel(key.field)}</dt>
                  <dd className="text-[13px] break-words text-muted">{key.where}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        <GuideFooter guide={guide} />
      </div>
    </details>
  )
}

/** A step of the route: its number on a small key tag, hung from the rail that joins the steps. */
function Step({ step, number, last, children }: { step: GuideStep; number: number; last: boolean; children?: ReactNode }) {
  const { t } = useTranslation('control')
  return (
    <li className="relative grid grid-cols-[1.75rem_minmax(0,1fr)] gap-3 pb-4 last:pb-0">
      {!last && <span aria-hidden className="absolute top-8 bottom-0 left-[0.8125rem] w-px bg-border-strong" />}
      <span
        aria-hidden
        className="num relative grid size-7 place-items-center rounded-md border border-border-strong bg-surface-2 pt-1 text-xs font-bold text-fg shadow-xs"
      >
        {/* the punched hole of a room key tag (the Housetel mark) */}
        <span className="absolute top-[3px] left-1/2 size-1 -translate-x-1/2 rounded-full bg-border-strong" />
        {number}
      </span>
      <div className="grid min-w-0 grid-cols-1 gap-1 pt-0.5">
        <p className="text-[13px] leading-5 font-bold text-fg">
          <span className="sr-only">{t('integrations.guide.stepLabel', { number })} </span>
          {step.title}
        </p>
        <p className="text-[13px] break-words text-muted">{step.body}</p>
        {step.link && (
          <a
            href={step.link.href}
            target="_blank"
            rel="noreferrer"
            className="inline-flex w-fit items-center gap-1 rounded-sm text-[13px] font-semibold text-accent-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          >
            {step.link.label}
            <ArrowUpRight aria-hidden className="size-3.5" />
            <span className="sr-only">{t('integrations.guide.newTab')}</span>
          </a>
        )}
        {children && <div className="mt-2 min-w-0">{children}</div>}
      </div>
    </li>
  )
}

/** Test vs live environment of the provider; the one chosen in the form is marked. */
function Environments({ guide, environment }: { guide: Guide; environment?: string | null }) {
  const { t } = useTranslation('control')
  const env = guide.environments
  if (!env) return null
  const chosen = environment ? (TEST_ENVIRONMENTS.has(environment) ? 'sandbox' : 'production') : null
  const items = [
    { id: 'sandbox' as const, label: env.sandboxLabel, text: env.sandbox, Icon: FlaskConical },
    { id: 'production' as const, label: env.productionLabel, text: env.production, Icon: Zap },
  ]
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {items.map(({ id, label, text, Icon }) => {
        const active = chosen === id
        return (
          <div key={id} className={cn('grid content-start gap-1 rounded-lg border p-3', active ? 'border-accent/45 bg-accent-soft/50' : 'border-border bg-surface-2/50')}>
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] font-bold text-fg">
              <Icon aria-hidden className={cn('size-4', active ? 'text-accent-ink' : 'text-muted')} />
              {label}
              {active && <span className="rounded-sm bg-accent-soft px-1.5 text-2xs font-semibold text-accent-ink">{t('integrations.guide.chosen')}</span>}
            </p>
            <p className="text-xs break-words text-muted">{text}</p>
          </div>
        )
      })}
    </div>
  )
}

/**
 * The URL the provider calls back (webhook), built on this installation's public address. While that address is
 * local (development), the provider cannot reach it: the box says so and gives the tunnel command.
 */
export function WebhookBox({ kind, path }: { kind: Integration['kind']; path: string }) {
  const { t } = useTranslation('control')
  const runtime = useRuntimeConfig()
  const url = webhookUrlFor(runtime.public_base_url, path)
  const local = isLocalUrl(url)
  return (
    <div className="grid min-w-0 grid-cols-1 gap-2 rounded-lg border border-border bg-surface-2/60 p-3">
      <p className="flex items-center gap-1.5 text-[13px] font-semibold text-fg">
        <Webhook aria-hidden className="size-4 text-muted" />
        {t('integrations.webhook.title')}
      </p>
      <div className="flex items-center gap-2">
        <code className="num min-w-0 flex-1 truncate rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-fg" title={url}>
          {url}
        </code>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-label={t('integrations.webhook.copy')}
          onClick={() => void copyText(url, t('integrations.webhook.copied'))}
        >
          <Copy aria-hidden />
        </Button>
      </div>
      <p className="text-xs text-muted">{t(`integrations.webhook.${kind}`, { defaultValue: '' })}</p>
      {local && (
        <div className="grid grid-cols-1 gap-2 rounded-md border border-warning/30 bg-warning-soft px-3 py-2 text-xs text-warning-ink">
          <p className="flex gap-2">
            <TriangleAlert aria-hidden className="mt-px size-3.5 shrink-0" />
            <span>{t('integrations.webhook.local')}</span>
          </p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded bg-surface px-2 py-1 font-mono text-[11.5px] text-fg" title={TUNNEL_COMMAND}>
              <SquareTerminal aria-hidden className="mr-1.5 inline size-3.5 align-[-2px] text-muted" />
              {TUNNEL_COMMAND}
            </code>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label={t('integrations.webhook.copyTunnel')}
              onClick={() => void copyText(TUNNEL_COMMAND, t('integrations.webhook.tunnelCopied'))}
            >
              <Copy aria-hidden />
            </Button>
          </div>
          <p>{t('integrations.webhook.localThen')}</p>
        </div>
      )}
    </div>
  )
}

/** The long guide (a documentation URL when the installation has one, else the file in the repository) and help. */
function GuideFooter({ guide }: { guide: Guide }) {
  const { t } = useTranslation('control')
  const { support } = useRuntimeConfig()
  const whatsapp = whatsappLink(support.whatsapp, t('integrations.guide.helpMessage', { provider: guide.provider }))
  const email = mailtoLink(support.email, t('integrations.guide.helpMessage', { provider: guide.provider }))
  return (
    <div className="grid grid-cols-1 gap-2 border-t border-border pt-3 text-[13px]">
      <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-muted">
        <BookOpenText aria-hidden className="size-4 shrink-0" />
        {support.docs_url ? (
          <a
            href={support.docs_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-sm font-semibold text-accent-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          >
            {t('integrations.guide.docsLink', { section: guide.docsSection })}
            <ArrowUpRight aria-hidden className="size-3.5" />
            <span className="sr-only">{t('integrations.guide.newTab')}</span>
          </a>
        ) : (
          <>
            {t('integrations.guide.docsFile')}
            <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs text-fg">{DOCS_PATH}</code>
            <span aria-hidden>›</span>
            <span className="font-semibold text-fg">{guide.docsSection}</span>
          </>
        )}
      </p>
      {hasSupportChannel(support) && (whatsapp || email) && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted">
          <LifeBuoy aria-hidden className="size-4 shrink-0" />
          {t('integrations.guide.help')}
          {whatsapp && (
            <a href={whatsapp} target="_blank" rel="noreferrer" className="font-semibold text-accent-ink hover:underline">
              {t('integrations.guide.helpWhatsapp')}
            </a>
          )}
          {email && (
            <a href={email} className="font-semibold text-accent-ink hover:underline">
              {support.email}
            </a>
          )}
        </p>
      )}
    </div>
  )
}
