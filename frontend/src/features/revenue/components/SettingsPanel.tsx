import { Lock } from 'lucide-react'
import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyInput } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useRevenueSettings, useSaveSettings, type RevenueSettings, type RevenueSettingsInput } from '../api'
import { Field } from './Field'

/** On/off and auto-apply (saved at once; turning auto-apply on asks first) and the limits of every run. */
export function SettingsPanel() {
  const settings = useRevenueSettings()
  if (settings.isPending) return <LoadingState variant="rows" rows={4} />
  if (settings.isError) return <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
  return <SettingsForm settings={settings.data} />
}

const plain = (value: string) => String(Number(value))

/** A setting that is a switch: the title names it, the hint describes it. */
function SwitchRow({
  label,
  hint,
  className,
  children,
}: {
  label: string
  hint: string
  className?: string
  children: (props: { id: string; 'aria-describedby': string }) => ReactNode
}) {
  const id = useId()
  return (
    <div className={cn('flex items-start justify-between gap-4', className)}>
      <div>
        <Label htmlFor={id} className="block text-sm">
          {label}
        </Label>
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      </div>
      {children({ id, 'aria-describedby': `${id}-hint` })}
    </div>
  )
}

function SettingsForm({ settings }: { settings: RevenueSettings }) {
  const { t } = useTranslation('revenue')
  const canManage = useCan('revenue.manage')
  const save = useSaveSettings()
  const [confirming, setConfirming] = useState(false)
  const [form, setForm] = useState({
    horizon_days: String(settings.horizon_days),
    max_daily_change_percent: plain(settings.max_daily_change_percent),
    min_change_percent: plain(settings.min_change_percent),
    price_rounding: plain(settings.price_rounding),
  })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)

  function toggle(body: RevenueSettingsInput, message: string) {
    return save.mutateAsync(body).then(
      () => {
        toast.success(message)
      },
      (error) => {
        toast.error(errorMessage(error, t))
      },
    )
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    setFieldErrors({})
    setFormError(null)
    save.mutate(
      {
        horizon_days: Number.parseInt(form.horizon_days, 10),
        max_daily_change_percent: form.max_daily_change_percent.replace(',', '.'),
        min_change_percent: form.min_change_percent.replace(',', '.'),
        price_rounding: form.price_rounding || '0',
      },
      {
        onSuccess: () => toast.success(t('settings.saved')),
        onError: (error) => {
          const fields = isApiError(error) ? (error.fields ?? {}) : {}
          setFieldErrors(Object.fromEntries(Object.entries(fields).map(([field, messages]) => [field, messages[0] ?? ''])))
          if (Object.keys(fields).length === 0) setFormError(errorMessage(error, t))
        },
      },
    )
  }

  const set = (field: keyof typeof form) => (value: string) => setForm((current) => ({ ...current, [field]: value }))

  return (
    <div className="grid max-w-3xl gap-5">
      {!canManage && (
        <p className="flex items-center gap-2 rounded-lg border border-border bg-surface-2 px-4 py-3 text-sm text-muted">
          <Lock aria-hidden className="size-4 shrink-0" />
          {t('settings.readOnly')}
        </p>
      )}

      <section aria-label={t('settings.title')} className="grid gap-4 rounded-lg border border-border bg-surface p-5 shadow-xs">
        <SwitchRow label={t('settings.enabled')} hint={t('settings.enabledHint')}>
          {(props) => (
            <Switch
              {...props}
              checked={settings.enabled}
              disabled={!canManage || save.isPending}
              onCheckedChange={(checked) => void toggle({ enabled: checked }, t(checked ? 'settings.enabledOn' : 'settings.enabledOff'))}
            />
          )}
        </SwitchRow>
        <SwitchRow label={t('settings.autoApply')} hint={t('settings.autoApplyHint')} className="border-t border-border pt-4">
          {(props) => (
            <Switch
              {...props}
              checked={settings.auto_apply}
              disabled={!canManage || save.isPending}
              onCheckedChange={(checked) => (checked ? setConfirming(true) : void toggle({ auto_apply: false }, t('settings.autoApplyOff')))}
            />
          )}
        </SwitchRow>
      </section>

      <form onSubmit={submit} noValidate className="grid gap-4 rounded-lg border border-border bg-surface p-5 shadow-xs">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t('settings.horizon')} hint={t('settings.horizonHint')} error={fieldErrors.horizon_days}>
            {(props) => (
              <Input {...props} inputMode="numeric" className="num" disabled={!canManage} value={form.horizon_days} onChange={(e) => set('horizon_days')(e.target.value)} />
            )}
          </Field>
          <Field label={t('settings.rounding')} hint={t('settings.roundingHint')} error={fieldErrors.price_rounding}>
            {(props) => <MoneyInput {...props} disabled={!canManage} value={form.price_rounding} onChange={set('price_rounding')} />}
          </Field>
          <Field label={t('settings.maxChange')} hint={t('settings.maxChangeHint')} error={fieldErrors.max_daily_change_percent}>
            {(props) => (
              <Input
                {...props}
                inputMode="decimal"
                className="num"
                disabled={!canManage}
                value={form.max_daily_change_percent}
                onChange={(e) => set('max_daily_change_percent')(e.target.value)}
              />
            )}
          </Field>
          <Field label={t('settings.minChange')} hint={t('settings.minChangeHint')} error={fieldErrors.min_change_percent}>
            {(props) => (
              <Input
                {...props}
                inputMode="decimal"
                className="num"
                disabled={!canManage}
                value={form.min_change_percent}
                onChange={(e) => set('min_change_percent')(e.target.value)}
              />
            )}
          </Field>
        </div>
        {formError && (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
            {formError}
          </p>
        )}
        {canManage && (
          <div className="flex justify-end border-t border-border pt-4">
            <Button type="submit" variant="primary" loading={save.isPending}>
              {t('settings.save')}
            </Button>
          </div>
        )}
      </form>

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t('settings.autoApplyConfirmTitle')}
        description={t('settings.autoApplyConfirm')}
        confirmLabel={t('settings.autoApplyConfirmButton')}
        onConfirm={async () => {
          await save.mutateAsync({ auto_apply: true })
          toast.success(t('settings.autoApplyOn'))
        }}
      />
    </div>
  )
}
