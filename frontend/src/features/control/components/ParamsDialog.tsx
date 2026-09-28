import { RotateCcw } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { useUpdateAutomation, type Automation, type ParamType } from '../api'
import { displayValue, humanize, localized } from '../lib/labels'

type Draft = Record<string, string | boolean>

function toDraft(type: ParamType, value: unknown): string | boolean {
  if (type === 'boolean') return Boolean(value)
  if (type === 'json') return JSON.stringify(value ?? null, null, 2)
  return value === null || value === undefined ? '' : String(value)
}

/** The automation's parameters as a form (one input per key of its defaults, typed like the default). */
export function ParamsDialog({ automation, open, onOpenChange }: { automation: Automation | null; open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        {automation && <ParamsForm key={automation.code} automation={automation} onClose={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function ParamsForm({ automation, onClose }: { automation: Automation; onClose: () => void }) {
  const { t, i18n } = useTranslation('control')
  const formId = useId()
  const update = useUpdateAutomation()
  const name = localized(automation.name, i18n.language)
  const keys = Object.keys(automation.param_types)
  const [draft, setDraft] = useState<Draft>(() =>
    Object.fromEntries(keys.map((key) => [key, toDraft(automation.param_types[key], automation.params[key])])),
  )
  const [errors, setErrors] = useState<Record<string, string>>({})
  const atDefaults = keys.every((key) => JSON.stringify(automation.params[key]) === JSON.stringify(automation.default_params[key]))

  const label = (key: string) =>
    i18n.exists(`automations.paramLabels.${key}`, { ns: 'control' }) ? t(`automations.paramLabels.${key}`) : humanize(key)

  function parse(): Record<string, unknown> | null {
    const next: Record<string, unknown> = {}
    const problems: Record<string, string> = {}
    for (const key of keys) {
      const type = automation.param_types[key]
      const value = draft[key]
      if (type === 'boolean') next[key] = Boolean(value)
      else if (type === 'integer' || type === 'number') {
        const number = Number(value)
        if (String(value).trim() === '' || !Number.isFinite(number) || (type === 'integer' && !Number.isInteger(number))) {
          problems[key] = t('validation.number', { ns: 'common' })
        } else next[key] = number
      } else if (type === 'json') {
        try {
          next[key] = JSON.parse(String(value))
        } catch {
          problems[key] = t('automations.paramsDialog.invalidJson')
        }
      } else next[key] = String(value)
    }
    setErrors(problems)
    return Object.keys(problems).length ? null : next
  }

  async function save(params: Record<string, unknown> | null) {
    try {
      await update.mutateAsync({ code: automation.code, body: { params } })
      toast.success(t('automations.toasts.paramsSaved', { name }))
      onClose()
    } catch (error) {
      if (isApiError(error) && error.fields) {
        const fieldErrors: Record<string, string> = {}
        for (const [field, messages] of Object.entries(error.fields)) {
          fieldErrors[field.replace(/^params\./, '')] = Array.isArray(messages) ? String(messages[0]) : String(messages)
        }
        setErrors(fieldErrors)
      }
      toast.error(errorMessage(error, t))
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const params = parse()
    if (params) void save(params)
  }

  return (
    <form id={formId} onSubmit={submit} className="grid min-w-0 gap-4">
      <DialogHeader>
        <DialogTitle>{t('automations.paramsDialog.title', { name })}</DialogTitle>
        <DialogDescription>{t('automations.paramsDialog.description')}</DialogDescription>
      </DialogHeader>

      <div className="grid gap-4">
        {keys.map((key) => {
          const type = automation.param_types[key]
          const inputId = `${formId}-${key}`
          const hint = t('automations.paramsDialog.defaultValue', { value: displayValue(automation.default_params[key], t) })
          const error = errors[key]
          if (type === 'boolean') {
            return (
              <div key={key} className="flex items-start justify-between gap-4 rounded-lg border border-border bg-surface-2/60 px-3 py-2.5">
                <div className="min-w-0">
                  <Label htmlFor={inputId}>{label(key)}</Label>
                  <p className="text-xs text-muted">{hint}</p>
                </div>
                <Switch
                  id={inputId}
                  name={key}
                  checked={Boolean(draft[key])}
                  onCheckedChange={(checked) => setDraft((current) => ({ ...current, [key]: checked }))}
                />
              </div>
            )
          }
          return (
            <div key={key} className="grid gap-1.5">
              <Label htmlFor={inputId}>{label(key)}</Label>
              {type === 'json' ? (
                <Textarea
                  id={inputId}
                  name={key}
                  rows={5}
                  spellCheck={false}
                  className="num font-mono text-xs"
                  value={String(draft[key])}
                  onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.value }))}
                  aria-invalid={error ? true : undefined}
                  aria-describedby={`${inputId}-hint`}
                />
              ) : (
                <Input
                  id={inputId}
                  name={key}
                  type={type === 'text' ? 'text' : 'number'}
                  step={type === 'integer' ? 1 : type === 'number' ? 'any' : undefined}
                  inputMode={type === 'integer' ? 'numeric' : type === 'number' ? 'decimal' : undefined}
                  className={type === 'text' ? undefined : 'num'}
                  value={String(draft[key])}
                  onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.value }))}
                  aria-invalid={error ? true : undefined}
                  aria-describedby={`${inputId}-hint`}
                />
              )}
              <p id={`${inputId}-hint`} className={error ? 'text-xs text-danger-ink' : 'text-xs text-muted'}>
                {error ?? hint}
              </p>
            </div>
          )
        })}
      </div>

      <DialogFooter className="sm:flex-wrap sm:justify-between">
        <Button type="button" variant="ghost" onClick={() => void save(null)} disabled={update.isPending || atDefaults}>
          <RotateCcw aria-hidden />
          {t('automations.paramsDialog.reset')}
        </Button>
        <div className="flex flex-col-reverse gap-2 sm:flex-row">
          <Button type="button" variant="secondary" onClick={onClose} disabled={update.isPending}>
            {t('actions.cancel', { ns: 'common' })}
          </Button>
          <Button type="submit" variant="primary" loading={update.isPending}>
            {t('automations.paramsDialog.save')}
          </Button>
        </div>
      </DialogFooter>
    </form>
  )
}
