import { Mail, MessageCircle, RotateCcw, Trash2 } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { isApiError } from '@/lib/api'
import { useActiveMembership } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  createTemplate,
  deleteTemplate,
  updateTemplate,
  useMessagingMutation,
  type EffectiveTemplate,
  type Language,
  type SendChannel,
  type TemplateInput,
  type Variable,
} from '../../api'
import { insertAtCursor } from '../../lib/thread'
import { Segmented } from '../Segmented'
import { TemplatePreview } from './TemplatePreview'
import { VariablePicker } from './VariablePicker'

type Scope = 'property' | 'organization'
const WHATSAPP_MAX = 4000
const SOURCE_TONE: Record<EffectiveTemplate['source'], BadgeTone> = { system: 'neutral', organization: 'info', property: 'accent' }

interface Draft {
  subject: string
  body: string
  is_active: boolean
  wa_template_name: string
  wa_params: string
}

function toDraft(row: EffectiveTemplate | undefined): Draft {
  return {
    subject: row?.subject ?? '',
    body: row?.body ?? '',
    is_active: row?.is_active ?? true,
    wa_template_name: row?.wa_template_name ?? '',
    wa_params: (row?.wa_template_params ?? []).join(', '),
  }
}

function sameDraft(a: Draft, b: Draft): boolean {
  return (Object.keys(a) as (keyof Draft)[]).every((key) => a[key] === b[key])
}

function parseParams(value: string): string[] {
  return value
    .split(/[,\s]+/)
    .map((item) => item.replace(/^\{\{|\}\}$/g, '').trim())
    .filter(Boolean)
}

/**
 * Editor of one template code: pick the channel and language, edit the text (with variables), see it as the
 * guest will, and save it for this hotel (or the whole organization). Saving the Housetel text creates the
 * hotel's own version; "back to the inherited text" deletes it.
 */
export function TemplateEditor({
  code,
  rows,
  variables,
  canEdit,
}: {
  code: string
  rows: EffectiveTemplate[]
  variables: Variable[]
  canEdit: boolean
}) {
  const { t, i18n } = useTranslation('messaging')
  const lang = normalizeLang(i18n.language)
  const [channel, setChannel] = useState<SendChannel>(() => (rows.some((row) => row.channel === 'email') || rows.length === 0 ? 'email' : 'whatsapp'))
  const [language, setLanguage] = useState<Language>(() =>
    rows.some((row) => row.language === lang && row.channel === channel) ? lang : (rows.find((row) => row.channel === channel)?.language ?? 'es'),
  )
  const dirty = useRef(false)
  const row = rows.find((item) => item.channel === channel && item.language === language)
  const first = rows[0]
  const label = first?.label[lang] || code

  function choose(next: { channel?: SendChannel; language?: Language }) {
    if (dirty.current && !window.confirm(t('settings.templates.discard'))) return
    dirty.current = false
    if (next.channel) setChannel(next.channel)
    if (next.language) setLanguage(next.language)
  }

  const controls = (
    <div className="flex flex-wrap items-center gap-2">
      <Segmented
        label={t('settings.templates.channel')}
        value={channel}
        onChange={(value) => choose({ channel: value })}
        options={[
          { value: 'email', label: t('channels.email'), icon: Mail },
          { value: 'whatsapp', label: t('channels.whatsapp'), icon: MessageCircle },
        ]}
      />
      <Segmented
        label={t('settings.templates.language')}
        value={language}
        onChange={(value) => choose({ language: value })}
        options={[
          { value: 'es', label: t('languages.es') },
          { value: 'en', label: t('languages.en') },
        ]}
      />
    </div>
  )

  return (
    <VariantForm
      key={`${channel}:${language}:${row?.id ?? 'system'}:${row?.updated_at ?? ''}`}
      code={code}
      label={label}
      customName={first?.is_system_code ? null : (first?.label.es ?? code)}
      isSystem={first?.is_system_code ?? false}
      channel={channel}
      language={language}
      row={row}
      variables={variables}
      canEdit={canEdit}
      controls={controls}
      onDirtyChange={(value) => {
        dirty.current = value
      }}
    />
  )
}

function VariantForm({
  code,
  label,
  customName,
  isSystem,
  channel,
  language,
  row,
  variables,
  canEdit,
  controls,
  onDirtyChange,
}: {
  code: string
  label: string
  customName: string | null
  isSystem: boolean
  channel: SendChannel
  language: Language
  row: EffectiveTemplate | undefined
  variables: Variable[]
  canEdit: boolean
  controls: ReactNode
  onDirtyChange: (dirty: boolean) => void
}) {
  const { t } = useTranslation('messaging')
  const ids = useId()
  const membership = useActiveMembership()
  const chain = (membership?.properties.length ?? 0) > 1
  const initial = toDraft(row)
  const [draft, setDraft] = useState<Draft>(initial)
  const defaultScope: Scope = row?.source === 'organization' ? 'organization' : 'property'
  const [scope, setScope] = useState<Scope>(defaultScope)
  const [confirming, setConfirming] = useState(false)
  const lastField = useRef<'subject' | 'body'>('body')
  const subjectRef = useRef<HTMLInputElement>(null)
  const bodyRef = useRef<HTMLTextAreaElement>(null)
  const dirty = !sameDraft(draft, initial) || scope !== defaultScope
  const source = row?.source ?? null
  const inheritsFrom: 'organization' | 'system' | null | undefined =
    source === 'property'
      ? row?.organization_template_id
        ? 'organization'
        : isSystem
          ? 'system'
          : null
      : source === 'organization'
        ? isSystem
          ? 'system'
          : null
        : undefined
  const rowId = source === 'property' ? row?.property_template_id : source === 'organization' ? row?.organization_template_id : null

  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange])

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((current) => ({ ...current, [key]: value }))

  const save = useMessagingMutation(
    () => {
      const payload: TemplateInput = {
        subject: channel === 'email' ? draft.subject : '',
        body: draft.body,
        is_active: draft.is_active,
        wa_template_name: channel === 'whatsapp' ? draft.wa_template_name.trim() : '',
        wa_template_params: channel === 'whatsapp' ? parseParams(draft.wa_params) : [],
      }
      if (source === 'property' && row?.property_template_id) return updateTemplate(row.property_template_id, payload)
      if (source === 'organization' && scope === 'organization' && row?.organization_template_id) {
        return updateTemplate(row.organization_template_id, payload)
      }
      return createTemplate({ code, ...(customName ? { name: customName } : {}), channel, language, scope, ...payload })
    },
    { onSuccess: () => toast.success(t('settings.templates.saved')) },
  )
  const remove = useMessagingMutation(() => deleteTemplate(rowId as string))

  function insertVariable(key: string) {
    const field = channel === 'email' ? lastField.current : 'body'
    const element = field === 'subject' ? subjectRef.current : bodyRef.current
    const { text, caret } = insertAtCursor(draft[field], `{{${key}}}`, element?.selectionStart ?? null, element?.selectionEnd ?? null)
    set(field, text)
    window.requestAnimationFrame(() => {
      element?.focus()
      element?.setSelectionRange(caret, caret)
    })
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!canEdit || !dirty) return
    save.mutate(undefined)
  }

  const fieldErrors = isApiError(save.error) ? (save.error.fields ?? {}) : {}
  const formError = save.error && !fieldErrors.subject && !fieldErrors.body ? errorMessage(save.error, t) : ''
  const sourceKey = source ?? (isSystem ? 'system' : null)

  return (
    <div className="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
      <form aria-label={label} onSubmit={submit} noValidate className="grid content-start gap-5 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5">
        <div className="grid gap-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <h2 className="text-[17px] leading-6 font-bold tracking-[-0.01em]">{label}</h2>
              <p className="num text-[12px] text-subtle">{code}</p>
            </div>
            {sourceKey ? (
              <Badge tone={SOURCE_TONE[sourceKey]}>{t(`settings.templates.sources.${sourceKey}`)}</Badge>
            ) : (
              <Badge tone="warning">{t('settings.templates.newVariant')}</Badge>
            )}
          </div>
          {controls}
          <p className="text-[12.5px] text-muted">
            {sourceKey ? t(`settings.templates.sourceHint.${sourceKey}`) : t('settings.templates.newVariantHint')}
          </p>
        </div>

        {channel === 'email' && (
          <div className="grid gap-1.5">
            <Label htmlFor={`${ids}-subject`}>{t('settings.templates.subject')}</Label>
            <Input
              ref={subjectRef}
              id={`${ids}-subject`}
              name="subject"
              value={draft.subject}
              disabled={!canEdit}
              onFocus={() => {
                lastField.current = 'subject'
              }}
              onChange={(event) => set('subject', event.target.value)}
              aria-invalid={Boolean(fieldErrors.subject) || undefined}
            />
            {fieldErrors.subject && <p className="text-[12.5px] text-danger-ink">{fieldErrors.subject.join(' ')}</p>}
          </div>
        )}

        <div className="grid gap-1.5">
          <div className="flex items-end justify-between gap-2">
            <Label htmlFor={`${ids}-body`}>{t('settings.templates.body')}</Label>
            <VariablePicker variables={variables} onPick={insertVariable} disabled={!canEdit} />
          </div>
          <Textarea
            ref={bodyRef}
            id={`${ids}-body`}
            name="body"
            rows={channel === 'email' ? 14 : 8}
            value={draft.body}
            disabled={!canEdit}
            onFocus={() => {
              lastField.current = 'body'
            }}
            onChange={(event) => set('body', event.target.value)}
            aria-describedby={`${ids}-body-hint`}
            aria-invalid={Boolean(fieldErrors.body) || undefined}
            className="min-h-40 resize-y text-[14px] leading-relaxed"
          />
          <div id={`${ids}-body-hint`} className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-[12px] text-muted">
            <span>{t('settings.templates.bodyHint')}</span>
            {channel === 'whatsapp' && (
              <span className={cn('num', draft.body.length > WHATSAPP_MAX && 'font-semibold text-danger-ink')}>
                {t('settings.templates.charCount', { count: draft.body.length, max: WHATSAPP_MAX })}
              </span>
            )}
          </div>
          {fieldErrors.body && <p className="text-[12.5px] text-danger-ink">{fieldErrors.body.join(' ')}</p>}
        </div>

        <div className="flex items-start justify-between gap-4 rounded-lg bg-surface-2 px-3 py-2.5">
          <div className="min-w-0">
            <Label htmlFor={`${ids}-active`}>{t('settings.templates.active')}</Label>
            <p className="text-[12.5px] text-muted">{t('settings.templates.activeHint')}</p>
          </div>
          <Switch id={`${ids}-active`} checked={draft.is_active} disabled={!canEdit} onCheckedChange={(value) => set('is_active', value)} />
        </div>

        {channel === 'whatsapp' && (
          <details className="group rounded-lg border border-border px-3 py-2.5 [&_summary::-webkit-details-marker]:hidden">
            <summary className="cursor-pointer list-none text-[13px] font-semibold">
              {t('settings.templates.wa.title')}
              {draft.wa_template_name && <span className="num ml-2 font-normal text-muted">{draft.wa_template_name}</span>}
            </summary>
            <div className="mt-3 grid gap-3">
              <p className="text-[12.5px] text-muted">{t('settings.templates.wa.hint', { first: '{{1}}', second: '{{2}}' })}</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label htmlFor={`${ids}-wa-name`}>{t('settings.templates.wa.name')}</Label>
                  <Input
                    id={`${ids}-wa-name`}
                    name="wa_template_name"
                    value={draft.wa_template_name}
                    disabled={!canEdit}
                    onChange={(event) => set('wa_template_name', event.target.value)}
                    className="num"
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor={`${ids}-wa-params`}>{t('settings.templates.wa.params')}</Label>
                  <Input
                    id={`${ids}-wa-params`}
                    name="wa_template_params"
                    value={draft.wa_params}
                    disabled={!canEdit}
                    placeholder={t('settings.templates.wa.paramsPlaceholder')}
                    onChange={(event) => set('wa_params', event.target.value)}
                    className="num"
                  />
                </div>
              </div>
            </div>
          </details>
        )}

        {chain && source !== 'property' && (
          <div className="grid gap-1.5">
            <p className="text-[13px] font-semibold">{t('settings.templates.scope')}</p>
            <Segmented
              label={t('settings.templates.scope')}
              value={scope}
              onChange={setScope}
              disabled={!canEdit}
              options={[
                { value: 'property', label: t('settings.templates.scopes.property') },
                { value: 'organization', label: t('settings.templates.scopes.organization') },
              ]}
            />
          </div>
        )}

        {formError && (
          <p role="alert" className="text-[13px] text-danger-ink">
            {formError}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
          {canEdit && inheritsFrom !== undefined && rowId && (
            <Button type="button" variant="ghost" size="sm" onClick={() => setConfirming(true)}>
              {inheritsFrom ? <RotateCcw aria-hidden /> : <Trash2 aria-hidden />}
              {inheritsFrom ? t('settings.templates.restore') : t('settings.templates.deleteVariant')}
            </Button>
          )}
          <span className="ml-auto flex items-center gap-3">
            {dirty && <span className="text-[12px] font-semibold text-warning-ink">{t('settings.templates.unsaved')}</span>}
            <Button type="submit" variant="primary" disabled={!canEdit || !dirty} loading={save.isPending}>
              {t('settings.templates.save')}
            </Button>
          </span>
        </div>
      </form>

      <TemplatePreview code={code} channel={channel} language={language} subject={draft.subject} body={draft.body} />

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={inheritsFrom ? t('settings.templates.restoreTitle') : t('settings.templates.deleteTitle')}
        description={
          inheritsFrom
            ? t('settings.templates.restoreDescription', { source: t(`settings.templates.inheritsFrom.${inheritsFrom}`) })
            : t('settings.templates.deleteDescription', { channel: t(`channels.${channel}`), language: t(`languages.${language}`) })
        }
        confirmLabel={t('common:actions.confirm')}
        onConfirm={async () => {
          await remove.mutateAsync(undefined)
          toast.success(inheritsFrom ? t('settings.templates.restored') : t('settings.templates.deleted'))
        }}
      />
    </div>
  )
}
