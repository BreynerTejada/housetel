import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { isExistingGuest, type GuestPickerValue } from '@/features/guests/api'
import { GuestPicker } from '@/features/guests/components/GuestPicker'
import { bookerIsForeignNonResident, type BookingSource, type StepErrors, type WizardState } from '../../lib/wizard'
import { FieldError } from './FieldError'

const SOURCES: BookingSource[] = ['front_desk', 'phone', 'email']

/** Step 3 — who holds the reservation (GuestPicker: search or create inline), how it came and its language. */
export function StepGuest({
  state,
  update,
  errors,
}: {
  state: WizardState
  update: (patch: Partial<WizardState>) => void
  errors: StepErrors
}) {
  const { t } = useTranslation('frontdesk')
  const ids = { guest: useId(), error: useId(), source: useId(), language: useId() }

  function pick(guest: GuestPickerValue | null) {
    const guestLanguage = guest && isExistingGuest(guest) ? guest.language : guest?.language
    const language = guestLanguage === 'en' ? 'en' : guestLanguage === 'es' ? 'es' : state.language
    // The backend applies the IVA exemption from the booker's data (foreign non-resident): quote with the
    // same treatment so the summary shows what will actually be charged. The rooms picked stay; the summary
    // and the offers re-price by themselves (the flag is part of their query).
    const foreign = bookerIsForeignNonResident(guest)
    update(foreign === null || foreign === state.foreign ? { guest, language } : { guest, language, foreign })
  }

  return (
    <div className="grid gap-6">
      <div className="grid gap-2">
        <Label htmlFor={ids.guest} className="font-semibold">
          {t('wizard.booker')}
        </Label>
        <GuestPicker
          id={ids.guest}
          value={state.guest}
          onChange={pick}
          aria-invalid={Boolean(errors.guest)}
          aria-describedby={errors.guest ? ids.error : undefined}
        />
        <FieldError id={ids.error} error={errors.guest} />
      </div>

      <div className="grid gap-4 border-t border-border pt-5 sm:grid-cols-2">
        {!state.walkIn && (
          <div className="grid gap-2">
            <p id={ids.source} className="font-semibold text-fg">
              {t('wizard.source')}
            </p>
            <ToggleGroup
              type="single"
              value={state.source}
              onValueChange={(value) => value && update({ source: value as BookingSource })}
              aria-labelledby={ids.source}
              className="w-max"
            >
              {SOURCES.map((source) => (
                <ToggleGroupItem key={source} value={source}>
                  {t(`sources.${source}`)}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
        )}
        <div className="grid gap-2">
          <Label htmlFor={ids.language} className="font-semibold">
            {t('wizard.language')}
          </Label>
          <Select value={state.language} onValueChange={(language) => update({ language: language as 'es' | 'en' })}>
            <SelectTrigger id={ids.language} className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="es">{t('common:languages.es')}</SelectItem>
              <SelectItem value="en">{t('common:languages.en')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  )
}
