import { Lock } from 'lucide-react'
import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { updateSettings, useHkMutation, useHkSettings, type HkSettings } from '../api'
import { formatDuration } from '../lib/time'

const FREQUENCIES = [1, 2, 3, 7, 0]
const MIN_SHIFT = 60
const MAX_SHIFT = 900

/** `/app/settings/housekeeping`: stayover frequency, inspection, auto-assignment and the length of a shift. */
export default function SettingsPage() {
  const { t } = useTranslation('housekeeping')
  const settings = useHkSettings()
  return (
    <div className="grid max-w-2xl grid-cols-1 gap-6">
      <PageHeader className="pb-0" title={t('settings.title')} description={t('settings.description')} />
      {settings.isPending ? (
        <LoadingState variant="rows" rows={4} />
      ) : settings.isError ? (
        <ErrorState error={settings.error} onRetry={() => settings.refetch()} />
      ) : (
        <SettingsForm key={JSON.stringify(settings.data)} saved={settings.data} />
      )}
    </div>
  )
}

function SettingsForm({ saved }: { saved: HkSettings }) {
  const { t } = useTranslation('housekeeping')
  const ids = useId()
  const canEdit = useCan('housekeeping.supervise')
  const [frequency, setFrequency] = useState(saved.stayover_frequency_days)
  const [inspection, setInspection] = useState(saved.require_inspection)
  const [autoAssign, setAutoAssign] = useState(saved.auto_assign)
  const [shift, setShift] = useState(String(saved.minutes_per_shift))
  const [shiftError, setShiftError] = useState(false)
  const save = useHkMutation((changes: Partial<HkSettings>) => updateSettings(changes), {
    onSuccess: () => toast.success(t('settings.saved')),
  })

  const shiftMinutes = Number(shift)
  const shiftValid = Number.isInteger(shiftMinutes) && shiftMinutes >= MIN_SHIFT && shiftMinutes <= MAX_SHIFT
  const options = FREQUENCIES.includes(frequency) ? FREQUENCIES : [...FREQUENCIES, frequency]

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!shiftValid) {
      setShiftError(true)
      return
    }
    const next: HkSettings = {
      stayover_frequency_days: frequency,
      require_inspection: inspection,
      auto_assign: autoAssign,
      minutes_per_shift: shiftMinutes,
    }
    const changes = Object.fromEntries(
      Object.entries(next).filter(([key, value]) => saved[key as keyof HkSettings] !== value),
    ) as Partial<HkSettings>
    if (Object.keys(changes).length > 0) save.mutate(changes)
  }

  return (
    <form onSubmit={submit} className="grid gap-5 rounded-xl border border-border bg-surface p-5 shadow-xs sm:p-6" noValidate>
      {!canEdit && (
        <p className="flex gap-2 rounded-lg bg-surface-2 px-3 py-2 text-sm text-muted">
          <Lock aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t('settings.readOnly')}
        </p>
      )}
      <Field id={`${ids}-frequency`} label={t('settings.frequency')} hint={t('settings.frequencyHint')}>
        <Select
          name="stayover_frequency_days"
          value={String(frequency)}
          onValueChange={(value) => setFrequency(Number(value))}
          disabled={!canEdit}
        >
          <SelectTrigger id={`${ids}-frequency`} className="sm:w-64" aria-describedby={`${ids}-frequency-hint`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map((days) => (
              <SelectItem key={days} value={String(days)}>
                {FREQUENCIES.includes(days) ? t(`settings.frequencyOptions.${days}`) : t('settings.everyN', { count: days })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Toggle
        id={`${ids}-inspection`}
        label={t('settings.inspection')}
        hint={t('settings.inspectionHint')}
        checked={inspection}
        onChange={setInspection}
        disabled={!canEdit}
      />
      <Toggle
        id={`${ids}-auto`}
        label={t('settings.autoAssign')}
        hint={t('settings.autoAssignHint')}
        checked={autoAssign}
        onChange={setAutoAssign}
        disabled={!canEdit}
      />
      <Field
        id={`${ids}-shift`}
        label={t('settings.shift')}
        hint={shiftValid ? t('settings.shiftHint', { time: formatDuration(shiftMinutes, t) }) : undefined}
        error={shiftError && !shiftValid ? t('settings.shiftRange') : undefined}
      >
        <Input
          id={`${ids}-shift`}
          name="minutes_per_shift"
          type="number"
          inputMode="numeric"
          min={MIN_SHIFT}
          max={MAX_SHIFT}
          step={15}
          value={shift}
          disabled={!canEdit}
          aria-invalid={(shiftError && !shiftValid) || undefined}
          aria-describedby={`${ids}-shift-hint`}
          onChange={(event) => setShift(event.target.value)}
          className="sm:w-40"
        />
      </Field>
      {save.isError && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {errorMessage(save.error, t)}
        </p>
      )}
      {canEdit && (
        <div>
          <Button type="submit" variant="primary" loading={save.isPending}>
            {t('settings.save')}
          </Button>
        </div>
      )}
    </form>
  )
}

function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {(error || hint) && (
        <p id={`${id}-hint`} className={error ? 'text-[13px] font-semibold text-danger-ink' : 'text-[13px] text-muted'}>
          {error ?? hint}
        </p>
      )}
    </div>
  )
}

function Toggle({
  id,
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  id: string
  label: string
  hint: string
  checked: boolean
  onChange: (checked: boolean) => void
  disabled: boolean
}) {
  return (
    <div className="flex items-start justify-between gap-6 border-t border-border pt-5">
      <div>
        <Label htmlFor={id}>{label}</Label>
        <p id={`${id}-hint`} className="mt-0.5 max-w-md text-[13px] text-muted">
          {hint}
        </p>
      </div>
      <Switch id={id} name={id} checked={checked} onCheckedChange={onChange} disabled={disabled} aria-describedby={`${id}-hint`} />
    </div>
  )
}
