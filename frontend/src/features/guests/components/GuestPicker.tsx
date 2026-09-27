/**
 * GuestPicker — choose the guest of a booking flow (exported for other features, e.g. the reservation
 * wizard of C1). See docs/integration-notes/B3-guests-team.md.
 *
 *   <GuestPicker value={booker} onChange={setBooker} />
 *
 * `onChange` receives an existing guest (`GuestSummary`, has `id`) or a new one (`GuestInput`, no `id`,
 * NOT saved: the booking API upserts it), or `null` when cleared. Use `isExistingGuest(value)` to tell them
 * apart. It never renders a <form>, so it can live inside the consumer's form.
 */
import { Search, Star, UserPlus } from 'lucide-react'
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from 'react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  DOCUMENT_TYPES,
  isExistingGuest,
  useGuestLookup,
  useGuestSearch,
  type DocumentType,
  type DuplicateGuest,
  type GuestInput,
  type GuestPickerValue,
  type GuestSummary,
} from '../api'
import { formatDocument, formatPhone, prefillFromQuery } from '../format'
import { useDebouncedValue } from '../hooks'
import { CountrySelect } from './CountrySelect'
import { GuestAvatar } from './GuestAvatar'

export interface GuestPickerProps {
  value: GuestPickerValue | null
  onChange: (value: GuestPickerValue | null) => void
  /** Id of the search input (for an external <label htmlFor>). */
  id?: string
  placeholder?: string
  disabled?: boolean
  /** Offer "create a new guest" (default true). */
  allowCreate?: boolean
  autoFocus?: boolean
  className?: string
  'aria-invalid'?: boolean
  'aria-describedby'?: string
}

const EMPTY_INPUT: GuestInput = {
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  document_type: 'CC',
  document_number: '',
  nationality: 'CO',
  country_of_residence: 'CO',
}

function summaryOf(guest: DuplicateGuest | GuestSummary): GuestSummary {
  const { reasons: _reasons, ...summary } = guest as DuplicateGuest
  return summary
}

export function GuestPicker({
  value,
  onChange,
  id,
  placeholder,
  disabled = false,
  allowCreate = true,
  autoFocus = false,
  className,
  ...aria
}: GuestPickerProps) {
  const [draft, setDraft] = useState<GuestInput | null>(null)
  const focusSearch = useRef(autoFocus)

  if (draft) {
    return (
      <NewGuestForm
        initial={draft}
        disabled={disabled}
        className={className}
        onCancel={() => {
          setDraft(null)
          focusSearch.current = true
        }}
        onUse={(input) => {
          setDraft(null)
          onChange(input)
        }}
        onUseExisting={(guest) => {
          setDraft(null)
          onChange(summaryOf(guest))
        }}
      />
    )
  }

  if (value) {
    return (
      <SelectedGuest
        value={value}
        disabled={disabled}
        className={className}
        onChange={() => {
          focusSearch.current = true
          onChange(null)
        }}
        onEdit={isExistingGuest(value) ? undefined : () => setDraft({ ...EMPTY_INPUT, ...value })}
      />
    )
  }

  return (
    <GuestSearch
      id={id}
      placeholder={placeholder}
      disabled={disabled}
      allowCreate={allowCreate}
      focusRef={focusSearch}
      className={className}
      aria={aria}
      onPick={(guest) => onChange(guest)}
      onCreate={(query) => setDraft({ ...EMPTY_INPUT, ...prefillFromQuery(query) })}
    />
  )
}

// ---- Search -------------------------------------------------------------------------------------

function GuestSearch({
  id,
  placeholder,
  disabled,
  allowCreate,
  focusRef,
  className,
  aria,
  onPick,
  onCreate,
}: {
  id?: string
  placeholder?: string
  disabled: boolean
  allowCreate: boolean
  focusRef: RefObject<boolean>
  className?: string
  aria: { 'aria-invalid'?: boolean; 'aria-describedby'?: string }
  onPick: (guest: GuestSummary) => void
  onCreate: (query: string) => void
}) {
  const { t } = useTranslation('guests')
  const generatedId = useId()
  const inputId = id ?? `${generatedId}-input`
  const listId = `${generatedId}-list`
  const inputRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const debounced = useDebouncedValue(query, 300)
  const search = useGuestSearch(debounced)
  const trimmed = query.trim()
  const results = trimmed && debounced.trim() ? (search.data?.results ?? []) : []
  const createIndex = allowCreate && trimmed ? results.length : -1
  const optionCount = results.length + (createIndex >= 0 ? 1 : 0)
  const expanded = open && trimmed.length > 0

  useEffect(() => {
    if (focusRef.current) {
      focusRef.current = false
      inputRef.current?.focus()
    }
  }, [focusRef])

  function choose(index: number) {
    const guest = results[index]
    if (guest) onPick(guest)
    else if (index === createIndex) onCreate(query)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      setOpen(true)
      if (optionCount) setActive((current) => (current + (event.key === 'ArrowDown' ? 1 : -1) + optionCount) % optionCount)
    } else if (event.key === 'Enter') {
      // A search box never submits the consumer's form (e.g. a reservation wizard step).
      event.preventDefault()
      if (expanded && optionCount) choose(Math.min(active, optionCount - 1))
    } else if (event.key === 'Escape' && expanded) {
      event.preventDefault()
      setOpen(false)
    }
  }

  const optionId = (index: number) => `${generatedId}-option-${index}`

  return (
    <div className={cn('relative', className)}>
      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
          <Input
            ref={inputRef}
            id={inputId}
            role="combobox"
            aria-label={t('picker.label')}
            aria-expanded={expanded}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={expanded && optionCount ? optionId(Math.min(active, optionCount - 1)) : undefined}
            aria-invalid={aria['aria-invalid']}
            aria-describedby={aria['aria-describedby']}
            autoComplete="off"
            spellCheck={false}
            disabled={disabled}
            value={query}
            placeholder={placeholder ?? t('picker.placeholder')}
            onChange={(event) => {
              setQuery(event.target.value)
              setActive(0)
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setOpen(false)}
            onKeyDown={onKeyDown}
            className="h-10 pl-9"
          />
        </div>
        {allowCreate && (
          <Button variant="secondary" className="h-10" disabled={disabled} onClick={() => onCreate(query)}>
            <UserPlus aria-hidden />
            <span className="max-sm:sr-only">{t('picker.create')}</span>
          </Button>
        )}
      </div>

      <div
        id={listId}
        role="listbox"
        aria-label={t('picker.results')}
        hidden={!expanded}
        className="absolute inset-x-0 top-full z-40 mt-1.5 max-h-80 overflow-y-auto rounded-lg border border-border bg-surface p-1 shadow-md"
      >
        {expanded && search.isFetching && results.length === 0 && (
          <p className="px-3 py-2.5 text-sm text-muted">{t('picker.searching')}</p>
        )}
        {expanded && !search.isFetching && debounced.trim() && results.length === 0 && (
          <p className="px-3 py-2.5 text-sm text-muted">{t('picker.noResults', { query: trimmed })}</p>
        )}
        {results.map((guest, index) => (
          <Option key={guest.id} id={optionId(index)} active={index === active} onChoose={() => choose(index)} onHover={() => setActive(index)}>
            <GuestLine guest={guest} />
          </Option>
        ))}
        {createIndex >= 0 && (
          <Option id={optionId(createIndex)} active={createIndex === active} onChoose={() => choose(createIndex)} onHover={() => setActive(createIndex)}>
            <span className="flex items-center gap-3 py-0.5 font-semibold text-accent-ink">
              <span className="grid size-8 place-items-center rounded-md border border-dashed border-accent/40 bg-accent-soft/60">
                <UserPlus aria-hidden className="size-4" />
              </span>
              {t('picker.createFrom', { query: trimmed })}
            </span>
          </Option>
        )}
      </div>
    </div>
  )
}

function Option({
  id,
  active,
  onChoose,
  onHover,
  children,
}: {
  id: string
  active: boolean
  onChoose: () => void
  onHover: () => void
  children: ReactNode
}) {
  return (
    <div
      id={id}
      role="option"
      aria-selected={active}
      tabIndex={-1}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onChoose}
      onMouseMove={onHover}
      className={cn('cursor-pointer rounded-md px-2 py-1.5 transition-colors', active && 'bg-surface-2')}
    >
      {children}
    </div>
  )
}

function GuestLine({ guest }: { guest: GuestSummary }) {
  const { t, i18n } = useTranslation('guests')
  const contact = [guest.email, formatPhone(guest.phone)].filter(Boolean).join(' · ')
  return (
    <span className="flex min-w-0 items-center gap-3">
      <GuestAvatar name={guest.full_name} vip={guest.is_vip} size="sm" />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="flex items-center gap-1.5 truncate font-semibold text-fg">
          {guest.full_name}
          {guest.is_vip && <Star aria-label={t('badges.vip')} className="size-3.5 fill-accent text-accent" />}
        </span>
        <span className="truncate text-xs text-muted">
          {[formatDocument(guest.document_type, guest.document_number), contact].filter(Boolean).join(' · ')}
        </span>
      </span>
      <span className="num hidden shrink-0 text-right text-xs text-subtle sm:block">
        {guest.last_stay_date
          ? formatDate(guest.last_stay_date, undefined, normalizeLang(i18n.language))
          : guest.stays_count
            ? t('picker.stays', { count: guest.stays_count })
            : t('picker.noStays')}
      </span>
    </span>
  )
}

// ---- Selected guest -----------------------------------------------------------------------------

function SelectedGuest({
  value,
  disabled,
  className,
  onChange,
  onEdit,
}: {
  value: GuestPickerValue
  disabled: boolean
  className?: string
  onChange: () => void
  onEdit?: () => void
}) {
  const { t } = useTranslation('guests')
  const name = isExistingGuest(value) ? value.full_name : [value.first_name, value.last_name].filter(Boolean).join(' ')
  const details = [
    formatDocument(value.document_type ?? '', value.document_number ?? ''),
    value.email,
    formatPhone(value.phone ?? ''),
  ].filter(Boolean)
  return (
    <div className={cn('flex items-center gap-3 rounded-lg border border-border bg-surface p-3 shadow-xs', className)}>
      <GuestAvatar name={name} vip={isExistingGuest(value) && value.is_vip} />
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 font-semibold text-fg">
          <span className="truncate">{name}</span>
          {isExistingGuest(value) && value.is_vip && <Badge tone="accent">{t('badges.vip')}</Badge>}
          {!isExistingGuest(value) && <Badge tone="info">{t('badges.new')}</Badge>}
        </p>
        {details.length > 0 && <p className="truncate text-xs text-muted">{details.join(' · ')}</p>}
      </div>
      {onEdit && (
        <Button variant="ghost" size="sm" disabled={disabled} onClick={onEdit} aria-label={t('picker.editLabel')}>
          {t('picker.edit')}
        </Button>
      )}
      <Button variant="secondary" size="sm" disabled={disabled} onClick={onChange} aria-label={t('picker.changeLabel')}>
        {t('picker.change')}
      </Button>
    </div>
  )
}

// ---- New guest ----------------------------------------------------------------------------------

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function NewGuestForm({
  initial,
  disabled,
  className,
  onCancel,
  onUse,
  onUseExisting,
}: {
  initial: GuestInput
  disabled: boolean
  className?: string
  onCancel: () => void
  onUse: (input: GuestInput) => void
  onUseExisting: (guest: DuplicateGuest) => void
}) {
  const { t } = useTranslation('guests')
  const baseId = useId()
  const [values, setValues] = useState<GuestInput>(initial)
  const [touched, setTouched] = useState(false)
  const lookup = useGuestLookup(useDebouncedValue(values, 400))
  const matches = (lookup.data ?? []).slice(0, 3)

  const firstNameError = touched && !values.first_name.trim() ? t('fields.firstNameRequired') : null
  const emailError = touched && values.email && !EMAIL.test(values.email.trim()) ? t('fields.emailInvalid') : null

  function set<K extends keyof GuestInput>(field: K, value: GuestInput[K]) {
    setValues((current) => {
      const next = { ...current, [field]: value }
      if (field === 'nationality') {
        const nationality = String(value || '')
        // A foreigner usually travels with a passport and lives where they come from.
        if (nationality && nationality !== 'CO' && current.document_type === 'CC') next.document_type = 'PA'
        if (nationality === 'CO' && current.document_type === 'PA') next.document_type = 'CC'
        if (!current.country_of_residence || current.country_of_residence === current.nationality) {
          next.country_of_residence = nationality
        }
      }
      return next
    })
  }

  function use() {
    setTouched(true)
    if (!values.first_name.trim() || (values.email && !EMAIL.test(values.email.trim()))) return
    const trimmed = Object.fromEntries(
      Object.entries(values).map(([key, value]) => [key, typeof value === 'string' ? value.trim() : value]),
    ) as unknown as GuestInput
    onUse({ ...trimmed, document_type: trimmed.document_number ? trimmed.document_type : '' })
  }

  const field = (name: string) => `${baseId}-${name}`

  return (
    <div
      role="group"
      aria-labelledby={field('title')}
      className={cn('grid gap-4 rounded-lg border border-border bg-surface p-4 shadow-xs', className)}
      onKeyDown={(event) => {
        // Only inputs of this group: key events from popovers (country search) bubble here through portals.
        const target = event.target as HTMLElement
        if (event.defaultPrevented || !event.currentTarget.contains(target)) return
        if (event.key === 'Enter' && target.tagName === 'INPUT') {
          event.preventDefault()
          use()
        }
      }}
    >
      <div>
        <p id={field('title')} className="font-bold text-fg">
          {t('picker.newTitle')}
        </p>
        <p className="text-xs text-muted">{t('picker.newHint')}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <TextField id={field('first')} label={t('fields.firstName')} value={values.first_name} error={firstNameError}
          onChange={(value) => set('first_name', value)} autoFocus disabled={disabled} autoComplete="off" />
        <TextField id={field('last')} label={t('fields.lastName')} value={values.last_name}
          onChange={(value) => set('last_name', value)} disabled={disabled} autoComplete="off" />
        <div className="grid gap-1.5">
          <Label htmlFor={field('doctype')}>{t('fields.documentType')}</Label>
          <Select
            name="guest_document_type"
            value={values.document_type || 'CC'}
            onValueChange={(value) => set('document_type', value as DocumentType)}
            disabled={disabled}
          >
            <SelectTrigger id={field('doctype')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DOCUMENT_TYPES.map((type) => (
                <SelectItem key={type} value={type}>
                  {t(`documentTypes.${type}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <TextField id={field('docnumber')} label={t('fields.documentNumber')} value={values.document_number ?? ''}
          onChange={(value) => set('document_number', value)} disabled={disabled} autoComplete="off" className="num" />
        <TextField id={field('email')} label={t('fields.email')} type="email" value={values.email ?? ''} error={emailError}
          onChange={(value) => set('email', value)} disabled={disabled} autoComplete="off" />
        <TextField id={field('phone')} label={t('fields.phone')} type="tel" value={values.phone ?? ''}
          onChange={(value) => set('phone', value)} disabled={disabled} autoComplete="off" hint={t('fields.phoneHint')} />
        <div className="grid gap-1.5">
          <Label htmlFor={field('nationality')}>{t('fields.nationality')}</Label>
          <CountrySelect id={field('nationality')} value={values.nationality ?? ''} onChange={(value) => set('nationality', value)} disabled={disabled} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={field('residence')}>{t('fields.residence')}</Label>
          <CountrySelect id={field('residence')} value={values.country_of_residence ?? ''}
            onChange={(value) => set('country_of_residence', value)} disabled={disabled} />
        </div>
      </div>

      {matches.length > 0 && <DuplicateWarning matches={matches} onUse={onUseExisting} />}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button variant="ghost" onClick={onCancel} disabled={disabled}>
          {t('actions.cancel', { ns: 'common' })}
        </Button>
        <Button variant="primary" onClick={use} disabled={disabled}>
          {t('picker.use')}
        </Button>
      </div>
    </div>
  )
}

function DuplicateWarning({ matches, onUse }: { matches: DuplicateGuest[]; onUse: (guest: DuplicateGuest) => void }) {
  const { t } = useTranslation('guests')
  return (
    <div role="status" aria-label={t('picker.duplicateTitle')} className="grid gap-2 rounded-lg border border-warning/30 bg-warning-soft/60 p-3">
      <p className="text-[13px] font-bold text-warning-ink">{t('picker.duplicateTitle')}</p>
      <p className="text-xs text-warning-ink">{t('picker.duplicateHint')}</p>
      <ul className="grid gap-1.5">
        {matches.map((match) => (
          <li key={match.id} className="flex items-center gap-3 rounded-md bg-surface/80 p-2">
            <GuestAvatar name={match.full_name} vip={match.is_vip} size="sm" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-semibold text-fg">{match.full_name}</p>
              <p className="flex flex-wrap gap-1 pt-0.5">
                {match.reasons.map((reason) => (
                  <Badge key={reason} tone="warning">
                    {t(`reasons.${reason}`)}
                  </Badge>
                ))}
              </p>
            </div>
            <Button size="sm" onClick={() => onUse(match)}>
              {t('picker.useExisting')}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function TextField({
  id,
  label,
  value,
  onChange,
  error,
  hint,
  className,
  ...props
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  error?: string | null
  hint?: string
  className?: string
  type?: string
  disabled?: boolean
  autoFocus?: boolean
  autoComplete?: string
}) {
  const describedBy = [error ? `${id}-error` : null, hint ? `${id}-hint` : null].filter(Boolean).join(' ') || undefined
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        name={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
        className={className}
        {...props}
      />
      {hint && !error && (
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="text-xs font-medium text-danger-ink" aria-live="polite">
          {error}
        </p>
      )}
    </div>
  )
}
