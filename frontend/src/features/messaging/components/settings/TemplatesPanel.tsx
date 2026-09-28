import { Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { normalizeLang, type Lang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useTemplates, useVariables, type EffectiveTemplate } from '../../api'
import { NewTemplateDialog } from './NewTemplateDialog'
import { TemplateEditor } from './TemplateEditor'

interface CodeGroup {
  code: string
  label: string
  system: boolean
  rows: EffectiveTemplate[]
}

function groupByCode(templates: EffectiveTemplate[], lang: Lang): CodeGroup[] {
  const groups = new Map<string, CodeGroup>()
  for (const row of templates) {
    const group = groups.get(row.code)
    if (group) group.rows.push(row)
    else groups.set(row.code, { code: row.code, label: row.label[lang] || row.code, system: row.is_system_code, rows: [row] })
  }
  return [...groups.values()]
}

/** One short line about a template in the list: customized for this hotel / by the organization / switched off. */
function useStateLine(group: CodeGroup): { text: string; tone: string } | null {
  const { t } = useTranslation('messaging')
  const off = [...new Set(group.rows.filter((row) => !row.is_active).map((row) => t(`channels.${row.channel}`)))]
  if (off.length) return { text: t('settings.templates.inactiveIn', { channels: off.join(', ') }), tone: 'text-warning-ink' }
  if (group.rows.some((row) => row.source === 'property')) return { text: t('settings.templates.customizedHotel'), tone: 'text-accent-ink' }
  if (group.rows.some((row) => row.source === 'organization')) return { text: t('settings.templates.customizedOrg'), tone: 'text-info-ink' }
  return null
}

function CodeButton({ group, selected, onSelect }: { group: CodeGroup; selected: boolean; onSelect: () => void }) {
  const line = useStateLine(group)
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? 'true' : undefined}
      className={cn(
        'grid gap-0.5 rounded-md px-2.5 py-1.5 text-left whitespace-nowrap transition-colors hover:bg-surface-2 lg:w-full lg:py-2 lg:whitespace-normal',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
        selected && 'bg-surface shadow-xs ring-1 ring-border hover:bg-surface',
      )}
    >
      <span className={cn('text-[13px] leading-5', selected ? 'font-bold text-fg' : 'font-medium text-fg')}>{group.label}</span>
      {line && <span className={cn('hidden text-[11px] leading-4 lg:block', line.tone)}>{line.text}</span>}
    </button>
  )
}

/** Tab "Templates": the list of messages (lifecycle ones first, then the hotel's own) and the editor. */
export function TemplatesPanel({ canEdit }: { canEdit: boolean }) {
  const { t, i18n } = useTranslation('messaging')
  const lang = normalizeLang(i18n.language)
  const [params, setParams] = useSearchParams()
  const templates = useTemplates()
  const variables = useVariables()
  const [creating, setCreating] = useState(false)
  const groups = useMemo(() => groupByCode(templates.data ?? [], lang), [templates.data, lang])

  if (templates.isPending) return <LoadingState variant="rows" rows={6} />
  if (templates.isError) return <ErrorState error={templates.error} onRetry={() => templates.refetch()} />

  const requested = params.get('template')
  const selected = groups.find((group) => group.code === requested) ?? groups[0]
  const system = groups.filter((group) => group.system)
  const custom = groups.filter((group) => !group.system)

  function select(code: string) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.set('template', code)
        return next
      },
      { replace: true },
    )
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[14.5rem_minmax(0,1fr)]">
      {/* One list: a scrollable row of chips on phones and tablets, a column beside the editor on desktop. */}
      <nav aria-label={t('settings.templates.listLabel')} className="min-w-0 lg:sticky lg:top-20 lg:self-start">
        <ul className="-mx-4 flex items-center gap-1 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:-mx-6 sm:px-6 lg:mx-0 lg:grid lg:items-stretch lg:gap-0.5 lg:overflow-visible lg:px-0 lg:pb-0">
          <li className="hidden lg:block">
            <p className="eyebrow px-2.5 pb-1">{t('settings.templates.system')}</p>
          </li>
          {system.map((group) => (
            <li key={group.code} className="shrink-0">
              <CodeButton group={group} selected={group.code === selected?.code} onSelect={() => select(group.code)} />
            </li>
          ))}
          <li className="hidden lg:block">
            <p className="eyebrow px-2.5 pt-4 pb-1">{t('settings.templates.custom')}</p>
          </li>
          {custom.map((group) => (
            <li key={group.code} className="shrink-0">
              <CodeButton group={group} selected={group.code === selected?.code} onSelect={() => select(group.code)} />
            </li>
          ))}
          {custom.length === 0 && (
            <li className="hidden lg:block">
              <p className="px-2.5 text-[12px] text-muted">{t('settings.templates.noCustom')}</p>
            </li>
          )}
          <li className="shrink-0 lg:px-2.5 lg:pt-2">
            <Button type="button" variant="secondary" size="sm" onClick={() => setCreating(true)} disabled={!canEdit}>
              <Plus aria-hidden />
              {t('settings.templates.new')}
            </Button>
          </li>
        </ul>
      </nav>

      {selected && (
        <TemplateEditor key={selected.code} code={selected.code} rows={selected.rows} variables={variables.data ?? []} canEdit={canEdit} />
      )}

      <NewTemplateDialog open={creating} onOpenChange={setCreating} existingCodes={groups.map((group) => group.code)} onCreated={select} />
    </div>
  )
}
