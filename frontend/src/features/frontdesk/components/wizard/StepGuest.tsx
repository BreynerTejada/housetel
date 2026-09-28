import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { isExistingGuest, type GuestPickerValue } from '@/features/guests/api'
import { GuestPicker } from '@/features/guests/components/GuestPicker'
import type { BookingSource, StepErrors, WizardState } from '../../lib/wizard'
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
    const language = guest && isExistingGuest(guest) ? guest.language : guest?.language
    update({ guest, language: language === 'en' ? 'en' : language === 'es' ? 'es' : state.language })
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
