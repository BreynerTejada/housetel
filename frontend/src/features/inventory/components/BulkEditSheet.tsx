import { useMutation } from '@tanstack/react-query'
import { useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { api, isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { flattenFieldErrors } from '../lib/fieldErrors'
import { naturalCompare, tr } from '../lib/text'
import {
  HOUSEKEEPING_STATUSES,
  useInvalidateInventory,
  type CustomFieldDefinition,
  type CustomValue,
  type Room,
  type RoomType,
} from '../api'
import { CustomFieldInput } from './CustomFieldInput'
import { RoomKeyTag } from './RoomKeyTag'
import { ViewSelect } from './ViewSelect'

type Control = 'text' | 'number' | 'decimal' | 'boolean' | 'view' | 'status' | 'roomType' | 'custom'

interface BulkField {
  key: string
  label: string
  group: 'room' | 'category' | 'custom'
  control: Control
  /** Can go back to the category value (reset). */
  resettable: boolean
  definition?: CustomFieldDefinition
}

const ROOM_FIELDS: [string, Control][] = [
  ['floor', 'text'],
  ['building', 'text'],
  ['room_type', 'roomType'],
  ['is_active', 'boolean'],
  ['housekeeping_status', 'status'],
]
const CATEGORY_FIELDS: [string, Control][] = [
  ['view', 'view'],
  ['max_occupancy', 'number'],
  ['max_adults', 'number'],
  ['max_children', 'number'],
  ['base_occupancy', 'number'],
  ['size_m2', 'decimal'],
  ['accessible', 'boolean'],
  ['smoking_allowed', 'boolean'],
  ['housekeeping_minutes', 'number'],
]

/** Applies one change to every selected room (backend `rooms/bulk-update/`, all or nothing). */
export function BulkEditSheet({
  open,
  onOpenChange,
  rooms,
  roomTypes,
  definitions,
  onDone,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  rooms: Room[]
  roomTypes: RoomType[]
  definitions: CustomFieldDefinition[]
  onDone: () => void
}) {
  const { t, i18n } = useTranslation('inventory')
  const lang = i18n.language
  const invalidate = useInvalidateInventory()
  const fields = useMemo<BulkField[]>(
    () => [
      ...ROOM_FIELDS.map(([key, control]) => ({ key, control, label: t(`fields.${key}`), group: 'room' as const, resettable: false })),
      ...CATEGORY_FIELDS.map(([key, control]) => ({ key, control, label: t(`fields.${key}`), group: 'category' as const, resettable: true })),
      ...definitions
        .filter((definition) => definition.applies_to === 'room' || definition.applies_to === 'room_type')
        .map((definition) => ({
          key: `custom_values.${definition.key}`,
          control: 'custom' as const,
          label: tr(definition.label, lang),
          group: 'custom' as const,
          resettable: true,
          definition,
        })),
    ],
    [definitions, lang, t],
  )
  const [fieldKey, setFieldKey] = useState('')
  const [mode, setMode] = useState<'set' | 'reset'>('set')
  const [value, setValue] = useState<CustomValue>('')
  const [error, setError] = useState<string | null>(null)
  const ids = { field: useId(), value: useId() }
  const field = fields.find((candidate) => candidate.key === fieldKey)

  function reset(next: boolean) {
    if (!next) {
      setFieldKey('')
      setMode('set')
      setValue('')
      setError(null)
    }
    onOpenChange(next)
  }

  function chooseField(key: string) {
    const next = fields.find((candidate) => candidate.key === key)
    setFieldKey(key)
    setMode('set')
    setError(null)
    setValue(next?.control === 'boolean' ? true : next?.control === 'status' ? 'clean' : next?.control === 'roomType' ? (roomTypes[0]?.id ?? '') : '')
  }

  const valid =
    Boolean(field) &&
    (mode === 'reset' ||
      (field?.control === 'number' || field?.control === 'decimal'
        ? typeof value === 'number' && Number.isFinite(value) && value >= 0
        : field?.control === 'roomType'
          ? Boolean(value)
          : true))

  const apply = useMutation({
    mutationFn: () => {
      const payloadValue = field?.control === 'decimal' ? String(value) : value
      return api.post<{ updated: number }>('/inventory/rooms/bulk-update/', {
        ids: rooms.map((room) => room.id),
        set: mode === 'set' && field ? { [field.key]: payloadValue } : {},
        reset: mode === 'reset' && field ? [field.key] : [],
      })
    },
    onSuccess: (result) => {
      toast.success(t('bulkEdit.updated', { count: result.updated }))
      void invalidate()
      onDone()
      reset(false)
    },
    onError: (err) => {
      // the field messages say which rooms fail ("Ocupación inválida en 101, 201")
      const details = isApiError(err) ? Object.values(flattenFieldErrors(err.fields)).filter((message) => message !== err.message) : []
      setError([errorMessage(err, t), ...details].join(' · '))
    },
  })

  const sorted = [...rooms].sort((a, b) => naturalCompare(a.number, b.number))

  return (
    <Sheet open={open} onOpenChange={reset}>
      <SheetContent side="right" aria-describedby={undefined}>
        <form
          className="flex h-full flex-col"
          onSubmit={(event) => {
            event.preventDefault()
            if (valid) apply.mutate()
          }}
        >
          <SheetHeader>
            <SheetTitle>{t('bulkEdit.title')}</SheetTitle>
            <SheetDescription>{t('bulkEdit.description', { count: rooms.length })}</SheetDescription>
          </SheetHeader>
          <SheetBody className="grid content-start gap-5">
            <ul aria-label={t('bulkEdit.selected')} className="flex flex-wrap gap-1.5">
              {sorted.slice(0, 40).map((room) => (
                <li key={room.id}>
                  <RoomKeyTag number={room.number} status={room.housekeeping_status} inactive={!room.is_active} size="sm" />
                </li>
              ))}
              {sorted.length > 40 && <li className="self-center text-xs text-muted">+{sorted.length - 40}</li>}
            </ul>

            <div className="grid gap-1.5">
              <span id={ids.field} className="text-[13px] font-semibold">
                {t('bulkEdit.field')}
              </span>
              <Select name="field" value={fieldKey} onValueChange={chooseField}>
                <SelectTrigger aria-labelledby={ids.field}>
                  <SelectValue placeholder={t('bulkEdit.fieldPlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {(['room', 'category', 'custom'] as const).map((group) => {
                    const items = fields.filter((candidate) => candidate.group === group)
                    if (!items.length) return null
                    return (
                      <SelectGroup key={group}>
                        <SelectLabel>{t(`bulkEdit.groups.${group}`)}</SelectLabel>
                        {items.map((candidate) => (
                          <SelectItem key={candidate.key} value={candidate.key}>
                            {candidate.label}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>

            {field?.resettable && (
              <RadioGroup value={mode} onValueChange={(next) => setMode(next as 'set' | 'reset')} aria-label={t('bulkEdit.mode')}>
                <label className="flex items-center gap-2 text-sm">
                  <RadioGroupItem value="set" />
                  {t('bulkEdit.setOwn')}
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <RadioGroupItem value="reset" />
                  {field.definition?.applies_to === 'room' ? t('bulkEdit.clear') : t('bulkEdit.inherit')}
                </label>
              </RadioGroup>
            )}

            {field && mode === 'set' && (
              <div className="grid gap-1.5">
                <span id={ids.value} className="text-[13px] font-semibold">
                  {t('bulkEdit.value')}
                </span>
                <ValueControl field={field} value={value} onChange={setValue} labelledBy={ids.value} roomTypes={roomTypes} />
              </div>
            )}

            {field?.key === 'room_type' && <p className="text-xs text-muted">{t('bulkEdit.roomTypeHint')}</p>}
            {field?.key === 'is_active' && value === false && <p className="text-xs text-muted">{t('bulkEdit.deactivateHint')}</p>}
            {error && (
              <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
                {error}
              </p>
            )}
          </SheetBody>
          <SheetFooter>
            <Button variant="secondary" onClick={() => reset(false)}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" disabled={!valid} loading={apply.isPending}>
              {t('bulkEdit.apply', { count: rooms.length })}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  )
}

function ValueControl({
  field,
  value,
  onChange,
  labelledBy,
  roomTypes,
}: {
  field: BulkField
  value: CustomValue
  onChange: (value: CustomValue) => void
  labelledBy: string
  roomTypes: RoomType[]
}) {
  const { t, i18n } = useTranslation('inventory')
  switch (field.control) {
    case 'number':
    case 'decimal':
      return (
        <Input
          type="number"
          name="value"
          aria-labelledby={labelledBy}
          min={0}
          step={field.control === 'decimal' ? '0.5' : '1'}
          className="w-40"
          value={typeof value === 'number' && Number.isFinite(value) ? String(value) : ''}
          onChange={(event) => onChange(event.target.valueAsNumber)}
        />
      )
    case 'boolean':
      return (
        <label className="flex items-center gap-3 text-sm">
          <Switch name="value" aria-labelledby={labelledBy} checked={value === true} onCheckedChange={(checked) => onChange(checked)} />
          {value ? t('common.yes') : t('common.no')}
        </label>
      )
    case 'view':
      return <ViewSelect name="value" labelledBy={labelledBy} value={typeof value === 'string' ? value : ''} onChange={onChange} />
    case 'status':
      return (
        <Select name="value" value={String(value)} onValueChange={onChange}>
          <SelectTrigger aria-labelledby={labelledBy}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {HOUSEKEEPING_STATUSES.map((status) => (
              <SelectItem key={status} value={status}>
                {t(`common:status.room.${status}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )
    case 'roomType':
      return (
        <Select name="value" value={String(value)} onValueChange={onChange}>
          <SelectTrigger aria-labelledby={labelledBy}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {roomTypes.map((type) => (
              <SelectItem key={type.id} value={type.id}>
                {type.code} · {tr(type.name, i18n.language)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )
    case 'custom':
      return field.definition ? (
        <CustomFieldInput definition={field.definition} labelledBy={labelledBy} value={value} onChange={onChange} />
      ) : null
    default:
      return (
        <Input name="value" aria-labelledby={labelledBy} maxLength={50} value={typeof value === 'string' ? value : ''}
               onChange={(event) => onChange(event.target.value)} />
      )
  }
}
