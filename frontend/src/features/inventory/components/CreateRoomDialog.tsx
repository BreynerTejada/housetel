import { useMutation } from '@tanstack/react-query'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api, isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { useCustomFields, useInvalidateInventory, type CustomFieldDefinition, type CustomValues, type Room, type RoomType } from '../api'
import { flattenFieldErrors } from '../lib/fieldErrors'
import { inferFloor } from '../lib/roomNumbers'
import { tr } from '../lib/text'
import { CustomFieldInput } from './CustomFieldInput'

/** Room fields a new room cannot be created without: mandatory and with no default value. */
function mandatoryWithoutDefault(definitions: CustomFieldDefinition[] | undefined): CustomFieldDefinition[] {
  return (definitions ?? []).filter((definition) => definition.required && (definition.default_value ?? null) === null)
}

/**
 * One new room: category, number, floor and the mandatory room fields without a default; the editor opens
 * right after for the rest.
 */
export function CreateRoomDialog({
  open,
  onOpenChange,
  roomTypes,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  roomTypes: RoomType[]
}) {
  const { t, i18n } = useTranslation('inventory')
  const navigate = useNavigate()
  const invalidate = useInvalidateInventory()
  const mandatory = mandatoryWithoutDefault(useCustomFields('room').data)
  const [roomTypeId, setRoomTypeId] = useState(roomTypes[0]?.id ?? '')
  const [number, setNumber] = useState('')
  const [floor, setFloor] = useState('')
  const [customValues, setCustomValues] = useState<CustomValues>({})
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const ids = { type: useId(), number: useId(), floor: useId(), custom: useId() }

  function close(next: boolean) {
    if (!next) {
      setNumber('')
      setFloor('')
      setCustomValues({})
      setFieldErrors({})
    }
    onOpenChange(next)
  }

  const create = useMutation({
    mutationFn: () => {
      // a mandatory yes/no field left untouched means "no"
      const custom = Object.fromEntries(
        mandatory
          .map((definition) => [definition.key, customValues[definition.key] ?? (definition.field_type === 'boolean' ? false : null)] as const)
          .filter(([, value]) => value !== null && value !== ''),
      )
      return api.post<Room>('/inventory/rooms/', {
        room_type: roomTypeId,
        number: number.trim(),
        floor: floor.trim() || inferFloor(number),
        ...(mandatory.length ? { custom_values: custom } : {}),
      })
    },
    onSuccess: (room) => {
      toast.success(t('rooms.created', { number: room.number }))
      void invalidate()
      close(false)
      navigate(`/app/settings/rooms/${room.id}`)
    },
    onError: (err) => {
      const fields = isApiError(err) ? flattenFieldErrors(err.fields) : {}
      if (Object.keys(fields).length) setFieldErrors(fields)
      else toast.error(errorMessage(err, t))
    },
  })

  const shownKeys = new Set(['number', ...mandatory.map((definition) => `custom_values.${definition.key}`)])
  const otherErrors = Object.entries(fieldErrors).filter(([key]) => !shownKeys.has(key)).map(([, message]) => message)

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (number.trim() && roomTypeId) create.mutate()
          }}
        >
          <DialogHeader>
            <DialogTitle>{t('rooms.newTitle')}</DialogTitle>
            <DialogDescription>{t('rooms.newDescription')}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <span id={ids.type} className="text-[13px] font-semibold">
              {t('fields.room_type')}
            </span>
            <Select name="room_type" value={roomTypeId} onValueChange={setRoomTypeId}>
              <SelectTrigger aria-labelledby={ids.type}>
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
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <label htmlFor={ids.number} className="text-[13px] font-semibold">
                {t('fields.number')}
              </label>
              <Input id={ids.number} name="number" maxLength={20} value={number} autoFocus
                     aria-invalid={Boolean(fieldErrors.number)} aria-describedby={fieldErrors.number ? `${ids.number}-error` : undefined}
                     onChange={(event) => setNumber(event.target.value)} />
              {fieldErrors.number && <span id={`${ids.number}-error`} className="text-xs font-medium text-danger-ink">{fieldErrors.number}</span>}
            </div>
            <label className="grid gap-1.5" htmlFor={ids.floor}>
              <span className="text-[13px] font-semibold">{t('fields.floor')}</span>
              <Input id={ids.floor} name="floor" maxLength={20} value={floor} placeholder={inferFloor(number) || t('bulkCreate.floorAuto')}
                     onChange={(event) => setFloor(event.target.value)} />
            </label>
          </div>
          {mandatory.map((definition) => {
            const labelId = `${ids.custom}-${definition.key}`
            const error = fieldErrors[`custom_values.${definition.key}`]
            return (
              <div key={definition.id} role="group" aria-labelledby={labelId} className="grid gap-1.5">
                <span id={labelId} className="text-[13px] font-semibold">
                  {tr(definition.label, i18n.language)}
                  <span className="text-accent-ink"> *</span>
                </span>
                <CustomFieldInput
                  definition={definition}
                  labelledBy={labelId}
                  value={customValues[definition.key]}
                  onChange={(value) => setCustomValues((current) => ({ ...current, [definition.key]: value }))}
                />
                {error && <span className="text-xs font-medium text-danger-ink">{error}</span>}
              </div>
            )
          })}
          {otherErrors.length > 0 && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {otherErrors.join(' ')}
            </p>
          )}
          <DialogFooter>
            <Button variant="secondary" onClick={() => close(false)}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" disabled={!number.trim() || !roomTypeId} loading={create.isPending}>
              {t('rooms.createAndEdit')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
