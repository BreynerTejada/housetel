import { useMutation } from '@tanstack/react-query'
import { PencilLine, UserRoundCheck } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { useForm, useWatch, type Control, type FieldErrors, type Resolver } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { CountrySelect } from '@/features/guests/components/CountrySelect'
import { normalizeLang, toISODate } from '@/lib/format'
import { saveGuests, type CheckinPayload } from '../../api'
import { DOCUMENT_TYPES, guestEntries, guestFormsFrom, validateGuests, type GuestForm, type GuestFormValues } from '../../lib/checkin'
import { fieldErrors, portalError } from '../../lib/errors'
import { tr } from '../../lib/text'
import { StepActions, StepError } from './StepLayout'

type Field = keyof Omit<GuestForm, 'slot' | 'stay_id' | 'role' | 'guest_id' | 'known' | 'keep' | 'document_hint'>

function nest(flat: Record<string, string>): FieldErrors<GuestFormValues> {
  const guests: Record<number, Record<string, { type: string; message: string }>> = {}
  for (const [path, message] of Object.entries(flat)) {
    const [, index, field] = path.split('.')
    if (index === undefined || field === undefined) continue
    guests[Number(index)] ??= {}
    guests[Number(index)]![field] = { type: 'validate', message }
  }
  const list: (Record<string, { type: string; message: string }> | undefined)[] = []
  for (const [index, errors] of Object.entries(guests)) list[Number(index)] = errors
  return { guests: list } as unknown as FieldErrors<GuestFormValues>
}

/**
 * Step 1 — every guest of the booking (TRA/SIRE data). The booker comes prefilled with what the hotel
 * knows; companions the hotel already registered stay as they are unless the guest updates them.
 */
export function GuestsStep({ checkin, token, onSaved }: { checkin: CheckinPayload; token: string; onSaved: (payload: CheckinPayload) => void }) {
  const { t } = useTranslation('guestportal')
  const today = toISODate(new Date())
  const defaultValues = useMemo(() => ({ guests: guestFormsFrom(checkin) }), [checkin])
  const resolver: Resolver<GuestFormValues> = async (values) => {
    const errors = validateGuests(values.guests, today)
    return Object.keys(errors).length ? { values: {}, errors: nest(errors) } : { values, errors: {} }
  }
  const form = useForm<GuestFormValues>({ defaultValues, resolver })
  const [formError, setFormError] = useState<unknown>(null)
  const save = useMutation({
    mutationFn: (values: GuestFormValues) => saveGuests(token, guestEntries(values.guests)),
    onSuccess: onSaved,
    onError: (error) => {
      const fields = fieldErrors(error)
      for (const [path, message] of Object.entries(fields)) {
        if (path.startsWith('guests.')) form.setError(path as `guests.${number}.first_name`, { type: 'server', message })
      }
      setFormError(error)
    },
  })
  const multipleRooms = checkin.stays.filter((stay) => ['tentative', 'confirmed', 'checked_in'].includes(stay.status)).length > 1

  return (
    <form
      noValidate
      className="grid gap-5"
      onSubmit={form.handleSubmit((values) => {
        setFormError(null)
        save.mutate(values)
      })}
    >
      <p className="text-[15px] text-muted">{t('checkin.guests.lead')}</p>
      {defaultValues.guests.map((guest, index) => {
        const before = defaultValues.guests.slice(0, index + 1)
        const companionNumber = before.filter((item) => item.role === 'companion' && !item.child).length
        const childNumber = before.filter((item) => item.child).length
        const title =
          guest.role === 'booker'
            ? t('checkin.guests.booker')
            : guest.child
              ? t('checkin.guests.child', { n: childNumber })
              : t('checkin.guests.companion', { n: companionNumber })
        const stay = checkin.stays.find((item) => item.id === guest.stay_id)
        return (
          <GuestCard
            key={guest.slot}
            index={index}
            title={title}
            room={multipleRooms && stay ? stay.room_type.name : null}
            control={form.control}
            travelReasons={checkin.travel_reasons}
            onEdit={() => form.setValue(`guests.${index}.keep`, false)}
            today={today}
          />
        )
      })}
      <p className="text-[13px] text-muted">{t('checkin.guests.fewerGuests')}</p>
      {formError ? <StepError message={portalError(formError, t)} /> : null}
      <StepActions>
        <Button type="submit" variant="primary" size="lg" loading={save.isPending} className="w-full sm:w-auto">
          {t('checkin.saveContinue')}
        </Button>
      </StepActions>
    </form>
  )
}

function GuestCard({
  index,
  title,
  room,
  control,
  travelReasons,
  onEdit,
  today,
}: {
  index: number
  title: string
  room: Record<string, string> | null
  control: Control<GuestFormValues>
  travelReasons: string[]
  onEdit: () => void
  today: string
}) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const titleId = useId()
  const guest = useWatch({ control, name: `guests.${index}` })
  const booker = guest.role === 'booker'

  return (
    <section aria-labelledby={titleId} className="rounded-2xl border border-border bg-surface p-4 shadow-xs sm:p-5">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 id={titleId} className="text-base font-bold">
          {title}
        </h3>
        {room && <span className="text-[13px] text-muted">{tr(room, lang)}</span>}
        {guest.child && !guest.keep && <p className="w-full text-[13px] text-muted">{t('checkin.guests.childHint')}</p>}
      </header>

      {guest.known && guest.keep ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-surface-2 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <UserRoundCheck aria-hidden className="size-5 shrink-0 text-success-ink" />
            <div className="min-w-0">
              <p className="truncate font-semibold">
                {guest.first_name} {guest.last_name}
              </p>
              <p className="text-[13px] text-muted">
                {[guest.document_type, guest.document_hint].filter(Boolean).join(' ')} · {t('checkin.guests.registered')}
              </p>
            </div>
          </div>
          <Button size="sm" variant="ghost" onClick={onEdit}>
            <PencilLine aria-hidden />
            {t('checkin.guests.edit')}
          </Button>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField control={control} index={index} field="first_name" autoComplete={booker ? 'given-name' : 'off'} />
          <TextField control={control} index={index} field="last_name" autoComplete={booker ? 'family-name' : 'off'} />
          <FormField
            control={control}
            name={`guests.${index}.document_type`}
            label={t('fields.document_type')}
            render={({ field, id, ...aria }) => (
              <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id={id} aria-invalid={aria['aria-invalid']} aria-describedby={aria['aria-describedby']}>
                  <SelectValue placeholder={t('fields.choose')} />
                </SelectTrigger>
                <SelectContent>
                  {DOCUMENT_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {t(`documentTypes.${type}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <TextField
            control={control}
            index={index}
            field="document_number"
            inputMode={guest.document_type === 'PA' ? 'text' : 'numeric'}
            description={guest.known && guest.document_hint ? t('checkin.guests.endsIn', { hint: guest.document_hint }) : undefined}
          />
          <FormField
            control={control}
            name={`guests.${index}.nationality`}
            label={t('fields.nationality')}
            render={({ field, id, ...aria }) => (
              <CountrySelect id={id} value={field.value} onChange={field.onChange} aria-invalid={aria['aria-invalid']} />
            )}
          />
          <FormField
            control={control}
            name={`guests.${index}.country_of_residence`}
            label={t('fields.country_of_residence')}
            render={({ field, id, ...aria }) => (
              <CountrySelect id={id} value={field.value} onChange={field.onChange} aria-invalid={aria['aria-invalid']} />
            )}
          />
          <TextField control={control} index={index} field="city_of_residence" autoComplete={booker ? 'address-level2' : 'off'} optional />
          <TextField control={control} index={index} field="birth_date" type="date" max={today} autoComplete={booker ? 'bday' : 'off'} />
          {booker && (
            <>
              <TextField control={control} index={index} field="email" type="email" autoComplete="email" optional />
              <TextField control={control} index={index} field="phone" type="tel" autoComplete="tel" optional />
            </>
          )}
        </div>
      )}

      {booker && (
        <fieldset className="mt-5 grid gap-3 border-t border-border pt-4 sm:grid-cols-3">
          <legend className="float-left mb-1 w-full sm:col-span-3">
            <span className="block text-sm font-bold">{t('checkin.guests.travelTitle')}</span>
            <span className="block text-[13px] text-muted">{t('checkin.guests.travelHint')}</span>
          </legend>
          <FormField
            control={control}
            name={`guests.${index}.travel_reason`}
            label={t('fields.travel_reason')}
            render={({ field, id, ...aria }) => (
              <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id={id} aria-invalid={aria['aria-invalid']} aria-describedby={aria['aria-describedby']}>
                  <SelectValue placeholder={t('fields.choose')} />
                </SelectTrigger>
                <SelectContent>
                  {travelReasons.map((reason) => (
                    <SelectItem key={reason} value={reason}>
                      {t(`travelReasons.${reason}`, { defaultValue: reason })}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <TextField control={control} index={index} field="origin" />
          <TextField control={control} index={index} field="destination" />
        </fieldset>
      )}
    </section>
  )
}

function TextField({
  control,
  index,
  field: name,
  type = 'text',
  autoComplete,
  inputMode,
  max,
  optional = false,
  description,
}: {
  control: Control<GuestFormValues>
  index: number
  field: Field
  type?: string
  autoComplete?: string
  inputMode?: 'text' | 'numeric' | 'tel' | 'email'
  max?: string
  optional?: boolean
  description?: string
}) {
  const { t } = useTranslation('guestportal')
  return (
    <FormField
      control={control}
      name={`guests.${index}.${name}`}
      label={optional ? t('fields.optional', { label: t(`fields.${name}`) }) : t(`fields.${name}`)}
      description={description}
      render={({ field, ...a11y }) => (
        <Input
          {...field}
          {...a11y}
          value={String(field.value ?? '')}
          type={type}
          max={max}
          inputMode={inputMode}
          autoComplete={autoComplete}
          className="h-11 text-[15px] sm:h-10 sm:text-sm"
        />
      )}
    />
  )
}
