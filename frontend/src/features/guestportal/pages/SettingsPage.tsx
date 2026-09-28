import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Lock } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { getPortalSettings, portalKeys, updatePortalSettings, type PortalSettings } from '../api'

type Toggle = 'require_document_photo' | 'require_signature' | 'auto_approve_extras' | 'allow_guest_cancellation' | 'allow_guest_modification'

interface Draft extends Pick<PortalSettings, Toggle> {
  days: string
  termsEs: string
  termsEn: string
}

function toDraft(settings: PortalSettings): Draft {
  return {
    days: String(settings.checkin_opens_days_before),
    require_document_photo: settings.require_document_photo,
    require_signature: settings.require_signature,
    auto_approve_extras: settings.auto_approve_extras,
    allow_guest_cancellation: settings.allow_guest_cancellation,
    allow_guest_modification: settings.allow_guest_modification,
    termsEs: settings.terms.es ?? '',
    termsEn: settings.terms.en ?? '',
  }
}

const TOGGLES: Toggle[] = ['require_document_photo', 'require_signature', 'auto_approve_extras', 'allow_guest_cancellation', 'allow_guest_modification']

/** Only what the manager changed (PATCH). */
function changesOf(initial: PortalSettings, draft: Draft): Partial<Omit<PortalSettings, 'updated_at'>> {
  const changes: Partial<Omit<PortalSettings, 'updated_at'>> = {}
  if (Number(draft.days) !== initial.checkin_opens_days_before) changes.checkin_opens_days_before = Number(draft.days)
  for (const key of TOGGLES) if (draft[key] !== initial[key]) changes[key] = draft[key]
  if (draft.termsEs !== (initial.terms.es ?? '') || draft.termsEn !== (initial.terms.en ?? '')) {
    changes.terms = { es: draft.termsEs, en: draft.termsEn }
  }
  return changes
}

/** `/app/settings/guest-portal` — what guests can do from their booking link. */
export default function SettingsPage() {
  const { t } = useTranslation('guestportal')
  const settings = useQuery({ queryKey: portalKeys.settings, queryFn: getPortalSettings })
  return (
    <div className="grid max-w-3xl gap-2">
      <PageHeader title={t('settings.title')} description={t('settings.description')} />
      {settings.isPending ? (
        <LoadingState />
      ) : settings.isError ? (
        <ErrorState error={settings.error} onRetry={() => settings.refetch()} />
      ) : (
        <SettingsForm key={settings.data.updated_at} initial={settings.data} />
      )}
    </div>
  )
}

function SettingsForm({ initial }: { initial: PortalSettings }) {
  const { t } = useTranslation('guestportal')
  const canEdit = useCan('guestportal.manage')
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState(() => toDraft(initial))
  const [tried, setTried] = useState(false)
  const days = Number(draft.days)
  const daysInvalid = draft.days.trim() === '' || !Number.isInteger(days) || days < 0 || days > 60
  const changes = changesOf(initial, draft)
  const dirty = Object.keys(changes).length > 0
  const save = useMutation({
    mutationFn: () => updatePortalSettings(changes),
    onSuccess: (saved) => {
      queryClient.setQueryData(portalKeys.settings, saved)
      toast.success(t('settings.saved'))
    },
  })
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((current) => ({ ...current, [key]: value }))

  return (
    <form
      noValidate
      className="grid gap-8"
      onSubmit={(event) => {
        event.preventDefault()
        setTried(true)
        if (!daysInvalid && dirty) save.mutate()
      }}
    >
      {!canEdit && (
        <p className="flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2 text-[13px] text-muted">
          <Lock aria-hidden className="size-4 shrink-0" />
          {t('settings.readOnly')}
        </p>
      )}

      <Section title={t('settings.checkin')}>
        <Row
          label={t('settings.opensDays')}
          hint={t('settings.opensDaysHint')}
          invalid={tried && daysInvalid}
          control={(id, hintId) => (
            <Input
              id={id}
              name="checkin_opens_days_before"
              type="number"
              inputMode="numeric"
              min={0}
              max={60}
              value={draft.days}
              disabled={!canEdit}
              onChange={(event) => set('days', event.target.value)}
              aria-describedby={hintId}
              aria-invalid={tried && daysInvalid}
              className="num w-24 text-right"
            />
          )}
        />
        <ToggleRow draft={draft} name="require_document_photo" label={t('settings.requireDocument')} hint={t('settings.requireDocumentHint')} onChange={set} disabled={!canEdit} />
        <ToggleRow draft={draft} name="require_signature" label={t('settings.requireSignature')} hint={t('settings.requireSignatureHint')} onChange={set} disabled={!canEdit} />
      </Section>

      <Section title={t('settings.selfService')}>
        <ToggleRow draft={draft} name="auto_approve_extras" label={t('settings.autoApprove')} hint={t('settings.autoApproveHint')} onChange={set} disabled={!canEdit} />
        <ToggleRow draft={draft} name="allow_guest_cancellation" label={t('settings.allowCancel')} hint={t('settings.allowCancelHint')} onChange={set} disabled={!canEdit} />
        <ToggleRow draft={draft} name="allow_guest_modification" label={t('settings.allowModify')} hint={t('settings.allowModifyHint')} onChange={set} disabled={!canEdit} />
      </Section>

      <Section title={t('settings.terms')} description={t('settings.termsHint')}>
        <div className="grid gap-4 p-4 sm:grid-cols-2">
          <TermsField label={t('settings.termsEs')} name="terms_es" value={draft.termsEs} onChange={(value) => set('termsEs', value)} disabled={!canEdit} lang="es" />
          <TermsField label={t('settings.termsEn')} name="terms_en" value={draft.termsEn} onChange={(value) => set('termsEn', value)} disabled={!canEdit} lang="en" />
        </div>
      </Section>

      {save.isError && (
        <p role="alert" className="text-sm font-medium text-danger-ink">
          {errorMessage(save.error, t)}
        </p>
      )}
      {canEdit && (
        <div className="flex justify-end">
          <Button type="submit" variant="primary" disabled={!dirty} loading={save.isPending}>
            {t('common:actions.saveChanges')}
          </Button>
        </div>
      )}
    </form>
  )
}

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="grid gap-3">
      <div>
        <h2 id={id} className="text-base font-bold">
          {title}
        </h2>
        {description && <p className="text-[13px] text-muted">{description}</p>}
      </div>
      <div className="divide-y divide-border rounded-xl border border-border bg-surface">{children}</div>
    </section>
  )
}

function Row({
  label,
  hint,
  invalid = false,
  control,
}: {
  label: string
  hint: string
  invalid?: boolean
  control: (id: string, hintId: string) => ReactNode
}) {
  const id = useId()
  const hintId = `${id}-hint`
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3.5">
      <div className="min-w-0">
        <Label htmlFor={id}>{label}</Label>
        <p id={hintId} className={cn('text-[13px]', invalid ? 'font-medium text-danger-ink' : 'text-muted')}>
          {hint}
        </p>
      </div>
      {control(id, hintId)}
    </div>
  )
}

function ToggleRow({
  draft,
  name,
  label,
  hint,
  onChange,
  disabled,
}: {
  draft: Draft
  name: Toggle
  label: string
  hint: string
  onChange: (key: Toggle, value: boolean) => void
  disabled: boolean
}) {
  return (
    <Row
      label={label}
      hint={hint}
      control={(id, hintId) => (
        <Switch id={id} name={name} checked={draft[name]} onCheckedChange={(value) => onChange(name, value)} disabled={disabled} aria-describedby={hintId} />
      )}
    />
  )
}

function TermsField({
  label,
  name,
  value,
  onChange,
  disabled,
  lang,
}: {
  label: string
  name: string
  value: string
  onChange: (value: string) => void
  disabled: boolean
  lang: string
}) {
  const id = useId()
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Textarea id={id} name={name} lang={lang} value={value} maxLength={5000} rows={7} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
    </div>
  )
}
