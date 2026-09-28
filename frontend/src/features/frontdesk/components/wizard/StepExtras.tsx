import { Plus } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { nightsBetween } from '@/lib/format'
import { useExtras, type Extra } from '../../api'
import { tr } from '../../lib/labels'
import { defaultExtraQuantity, type StepErrors, type WizardState } from '../../lib/wizard'
import { FieldError } from './FieldError'

/** Step 4 — extras (charged to the folio right after the reservation is created), arrival time and notes. */
export function StepExtras({
  state,
  update,
  errors,
  currency,
}: {
  state: WizardState
  update: (patch: Partial<WizardState>) => void
  errors: StepErrors
  currency: string
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const extras = useExtras()
  const ids = { eta: useId(), etaError: useId(), requests: useId(), notes: useId() }
  const nights = Math.max(1, nightsBetween(state.checkin, state.checkout))
  const persons = state.adults + state.children

  function setQuantity(extra: Extra, quantity: number) {
    update({ extras: { ...state.extras, [extra.id]: quantity } })
  }

  return (
    <div className="grid gap-6">
      <section className="grid gap-2">
        <h3 className="eyebrow">{t('wizard.extras')}</h3>
        {extras.isError ? (
          <ErrorState error={extras.error} onRetry={() => extras.refetch()} />
        ) : !extras.data ? (
          <LoadingState variant="rows" rows={2} />
        ) : extras.data.results.length === 0 ? (
          <p className="text-[13px] text-muted">{t('wizard.noExtras')}</p>
        ) : (
          <ul className="grid gap-2">
            {extras.data.results.map((extra) => {
              const name = tr(extra.name, i18n.language)
              const quantity = state.extras[extra.id] ?? 0
              return (
                <li key={extra.id}>
                  <div
                    role="group"
                    aria-label={name}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border px-4 py-3"
                  >
                    <div className="min-w-0">
                      <p className="font-semibold text-fg">{name}</p>
                      <p className="text-[13px] text-muted">
                        <MoneyText value={extra.price} currency={currency} /> · {t(`chargeTypes.${extra.charge_type}`)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {quantity === 0 && (
                        <Button size="sm" onClick={() => setQuantity(extra, defaultExtraQuantity(extra.charge_type, nights, persons))}>
                          <Plus aria-hidden />
                          {t('wizard.addExtra')}
                        </Button>
                      )}
                      <Input
                        type="number"
                        min={0}
                        step={1}
                        inputMode="numeric"
                        value={quantity}
                        onChange={(event) => setQuantity(extra, Math.max(0, Math.trunc(Number(event.target.value) || 0)))}
                        aria-label={t('wizard.quantityOf', { name })}
                        className="num h-8 w-20 text-right"
                      />
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
        <FieldError error={errors.extras} />
        <p className="text-xs text-muted">{t('wizard.extrasHint')}</p>
      </section>

      <div className="grid gap-4 border-t border-border pt-5 sm:grid-cols-[12rem_minmax(0,1fr)]">
        <div className="grid content-start gap-2">
          <Label htmlFor={ids.eta} className="font-semibold">
            {t('wizard.eta')}
          </Label>
          <Input
            id={ids.eta}
            value={state.eta}
            onChange={(event) => update({ eta: event.target.value.replace(/[^\d:]/g, '').slice(0, 5) })}
            placeholder="HH:MM"
            inputMode="numeric"
            autoComplete="off"
            aria-invalid={Boolean(errors.eta)}
            aria-describedby={errors.eta ? ids.etaError : undefined}
            className="num w-28"
          />
          <FieldError id={ids.etaError} error={errors.eta} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor={ids.requests} className="font-semibold">
            {t('wizard.specialRequests')}
          </Label>
          <Textarea
            id={ids.requests}
            value={state.specialRequests}
            onChange={(event) => update({ specialRequests: event.target.value })}
            placeholder={t('wizard.specialRequestsPlaceholder')}
            rows={2}
          />
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor={ids.notes} className="font-semibold">
          {t('wizard.notes')}
        </Label>
        <Textarea id={ids.notes} value={state.notes} onChange={(event) => update({ notes: event.target.value })} placeholder={t('wizard.notesPlaceholder')} rows={2} />
      </div>
    </div>
  )
}
