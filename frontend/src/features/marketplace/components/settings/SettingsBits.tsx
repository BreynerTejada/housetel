import { Check, Copy } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** A settings block: title and hint on the left, fields on the right (stacked on phones). */
export function SettingsSection({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-border py-6 first:border-t-0 first:pt-0 md:grid-cols-[13rem_minmax(0,1fr)] md:gap-8">
      <div>
        <h2 className="text-[15px] font-bold text-fg">{title}</h2>
        {hint && <p className="mt-1 text-[13px] text-muted">{hint}</p>}
      </div>
      <div className="grid min-w-0 gap-4">{children}</div>
    </section>
  )
}

/** Sticky bar shown while a form has unsaved changes. */
export function SaveBar({ visible, saving, onSave, onDiscard }: { visible: boolean; saving: boolean; onSave: () => void; onDiscard: () => void }) {
  const { t } = useTranslation(['marketplace', 'common'])
  if (!visible) return null
  return (
    <div
      role="region"
      aria-label={t('settings.unsaved')}
      className="sticky bottom-4 z-20 mt-2 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-surface/95 px-4 py-3 shadow-lg backdrop-blur animate-pop-in"
    >
      <p className="flex min-w-0 flex-1 items-center gap-2 text-[13px] font-semibold text-fg">
        <span aria-hidden className="size-2 rounded-full bg-accent" />
        <span className="truncate">{t('settings.unsaved')}</span>
      </p>
      <Button variant="ghost" size="sm" onClick={onDiscard} disabled={saving}>
        {t('settings.discard')}
      </Button>
      <Button variant="primary" size="sm" onClick={onSave} loading={saving}>
        {t('common:actions.saveChanges')}
      </Button>
    </div>
  )
}

/** A value with a copy button (links and HTML snippets). */
export function CopyBlock({ label, hint, value, code = false }: { label: string; hint?: string; value: string; code?: boolean }) {
  const { t } = useTranslation('marketplace')
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      toast.success(t('settings.embed.copied'))
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      /* clipboard blocked: the text stays selectable */
    }
  }
  return (
    <div role="group" aria-label={label} className="grid gap-1.5">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-[13px] font-semibold text-fg">{label}</p>
          {hint && <p className="text-xs text-muted">{hint}</p>}
        </div>
        <Button size="sm" onClick={() => void copy()}>
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
          {copied ? t('settings.embed.copied') : t('settings.embed.copy')}
        </Button>
      </div>
      <pre
        className={cn(
          'overflow-x-auto rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-xs leading-relaxed whitespace-pre-wrap text-fg [overflow-wrap:anywhere]',
          code && 'font-mono',
        )}
      >
        {value}
      </pre>
    </div>
  )
}
