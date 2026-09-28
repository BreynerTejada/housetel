import { ArrowUpRight, BookOpenText, Check, Copy, Mail, MessageCircle, type LucideIcon } from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useRuntimeConfig } from '@/lib/runtime'
import { cn } from '@/lib/utils'
import { contextLines, supportLinks, supportMessage, useSupportContext } from './support'

interface ChannelProps {
  href: string
  icon: LucideIcon
  label: string
  value: string
  hint: string
  action: string
  featured?: boolean
}

/**
 * One way to reach support, drawn as a key tag from the front-desk rack (the punched hole on the left): the
 * whole tag is the link. WhatsApp is the featured tag — it is how hotels in Colombia talk to their providers.
 */
function Channel({ href, icon: Icon, label, value, hint, action, featured = false }: ChannelProps) {
  const external = !href.startsWith('mailto:')
  return (
    <li>
      <a
        href={href}
        target={external ? '_blank' : undefined}
        rel={external ? 'noopener noreferrer' : undefined}
        aria-label={`${label}: ${action}${value ? ` (${value})` : ''}`}
        className={cn(
          'group relative flex items-center gap-3 rounded-lg border py-3 pr-3 pl-7 transition-[border-color,background-color,box-shadow]',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:ring-offset-2 focus-visible:ring-offset-surface',
          featured
            ? 'border-accent/30 bg-accent-soft hover:border-accent/55'
            : 'border-border bg-surface hover:border-border-strong hover:bg-surface-2',
        )}
      >
        <span
          aria-hidden
          className={cn(
            'absolute top-1/2 left-2.5 size-2.5 -translate-y-1/2 rounded-full border bg-bg',
            featured ? 'border-accent/45' : 'border-border-strong',
          )}
        />
        <span
          aria-hidden
          className={cn(
            'grid size-9 shrink-0 place-items-center rounded-md',
            featured ? 'bg-surface text-accent-ink' : 'bg-surface-2 text-muted group-hover:text-fg',
          )}
        >
          <Icon className="size-[18px]" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-bold text-fg">{label}</span>
          <span className="block truncate text-xs text-muted">{value ? <span className="num">{value}</span> : hint}</span>
          {value && <span className="mt-0.5 hidden text-xs text-muted sm:block">{hint}</span>}
        </span>
        <span
          aria-hidden
          className={cn(
            'inline-flex shrink-0 items-center gap-1 text-[13px] font-semibold',
            featured ? 'text-accent-ink' : 'text-muted group-hover:text-fg',
          )}
        >
          <span className="hidden sm:inline">{action}</span>
          <ArrowUpRight className="size-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 motion-reduce:transition-none" />
        </span>
      </a>
    </li>
  )
}

/** "Help and support" (user menu of the staff shells): the support channels of this installation and the
 * details that go with the message, so nobody has to ask which hotel or screen it was. */
export function SupportDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation()
  const { support } = useRuntimeConfig()
  const context = useSupportContext()
  const links = supportLinks(support, context, t)
  const lines = contextLines(context, t)
  const [copied, setCopied] = useState(false)
  const channels = useRef<HTMLUListElement>(null)
  const hasChannel = Boolean(links.whatsapp || links.email || links.docs)

  // Radix focuses the first button (it skips links); the first channel is the action people came for.
  function focusFirstChannel(event: Event) {
    const first = channels.current?.querySelector('a')
    if (!first) return
    event.preventDefault()
    first.focus()
  }

  async function copyDetails() {
    try {
      await navigator.clipboard.writeText(supportMessage(context, t))
      setCopied(true)
      toast.success(t('support.copied'))
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(t('errors.generic'))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md gap-5" onOpenAutoFocus={focusFirstChannel}>
        <DialogHeader>
          <DialogTitle>{t('support.title')}</DialogTitle>
          <DialogDescription>{t('support.description')}</DialogDescription>
        </DialogHeader>

        {hasChannel ? (
          <ul ref={channels} className="grid gap-2">
            {links.whatsapp && (
              <Channel
                featured
                href={links.whatsapp}
                icon={MessageCircle}
                label={t('support.whatsapp')}
                value={support.whatsapp}
                hint={t('support.whatsappHint')}
                action={t('support.whatsappAction')}
              />
            )}
            {links.email && (
              <Channel
                featured={!links.whatsapp}
                href={links.email}
                icon={Mail}
                label={t('support.email')}
                value={support.email}
                hint={t('support.emailHint')}
                action={t('support.emailAction')}
              />
            )}
            {links.docs && (
              <Channel
                href={links.docs}
                icon={BookOpenText}
                label={t('support.docs')}
                value=""
                hint={t('support.docsHint')}
                action={t('support.docsAction')}
              />
            )}
          </ul>
        ) : (
          <p className="rounded-lg border border-dashed border-border-strong bg-surface-2 px-4 py-3 text-sm text-muted">
            {t('support.none')}
          </p>
        )}

        {lines.length > 0 && (
          <section aria-labelledby="support-context-title" className="rounded-lg border border-border bg-surface-2/60 p-3.5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 id="support-context-title" className="eyebrow">
                  {t('support.contextTitle')}
                </h3>
                <p className="mt-0.5 text-xs text-muted">{t('support.contextHint')}</p>
              </div>
              <Button type="button" variant="ghost" size="sm" onClick={() => void copyDetails()} className="-mt-1 -mr-1.5">
                {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
                {copied ? t('support.copied') : t('support.copy')}
              </Button>
            </div>
            <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-[13px]">
              {lines.map(([label, value]) => (
                <div key={label} className="contents">
                  <dt className="text-muted">{label}</dt>
                  <dd className="num truncate text-fg" title={value}>
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        )}
      </DialogContent>
    </Dialog>
  )
}
