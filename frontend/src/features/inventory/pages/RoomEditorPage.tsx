import { useMutation } from '@tanstack/react-query'
import { Ban, RotateCcw } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { api, isApiError } from '@/lib/api'
import { useActiveMembership } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import {
  OVERRIDABLE_FIELDS,
  useAmenities,
  useCustomFields,
  useInvalidateInventory,
  useRoom,
  useRoomTypes,
  type Amenity,
  type CategoryAttributes,
  type CustomFieldDefinition,
  type CustomValue,
  type CustomValues,
  type OverridableField,
  type Room,
  type RoomOverrides,
  type RoomType,
} from '../api'
import { AmenityPicker } from '../components/AmenityPicker'
import { BedConfigEditor } from '../components/BedConfigEditor'
import { CategoryChip } from '../components/CategoryChip'
import { CustomFieldInput } from '../components/CustomFieldInput'
import { I18nTextInput } from '../components/I18nTextInput'
import { InheritedField } from '../components/InheritedField'
import { RoomBedsPanel } from '../components/RoomBedsPanel'
import { RoomBlocksPanel } from '../components/RoomBlocksPanel'
import { RoomKeyTag } from '../components/RoomKeyTag'
import { RoomStatusBadge } from '../components/RoomStatusBadge'
import { SaveBar } from '../components/SaveBar'
import { TabErrorDot } from '../components/TabErrorDot'
import { ViewSelect } from '../components/ViewSelect'
import { attributeText, OCCUPANCY_FIELDS, occupancyErrors, type OccupancyField } from '../lib/attributes'
import { customValueText } from '../lib/customValues'
import { flattenFieldErrors, withoutErrors } from '../lib/fieldErrors'
import { tr } from '../lib/text'
import { useServerDraft } from '../lib/useServerDraft'

interface Draft {
  number: string
  name: string
  floor: string
  building: string
  notes: string
  is_active: boolean
  room_type: string
  overrides: RoomOverrides
  extra_amenities: string[]
  removed_amenities: string[]
  custom_values: CustomValues
}

function draftOf(room: Room): Draft {
  return {
    number: room.number,
    name: room.name,
    floor: room.floor,
    building: room.building,
    notes: room.notes,
    is_active: room.is_active,
    room_type: room.room_type,
    overrides: { ...room.overrides },
    extra_amenities: [...room.extra_amenities],
    removed_amenities: [...room.removed_amenities],
    custom_values: { ...room.custom_values },
  }
}

const NUMBER_FIELDS: OverridableField[] = ['base_occupancy', 'max_adults', 'max_children', 'max_occupancy', 'housekeeping_minutes']

export default function RoomEditorPage() {
  const { roomId } = useParams()
  const { t } = useTranslation('inventory')
  const room = useRoom(roomId)
  const roomTypes = useRoomTypes()
  const amenities = useAmenities()
  const definitions = useCustomFields()
  const membership = useActiveMembership() // permissions decide what is editable: wait for them

  const breadcrumbs = [{ label: t('nav.rooms'), to: '/app/settings/rooms' }, { label: room.data?.number ?? '…' }]
  if (room.isError || roomTypes.isError) {
    return (
      <>
        <PageHeader title={t('roomEditor.title', { number: '' })} breadcrumbs={breadcrumbs} />
        <ErrorState error={room.error ?? roomTypes.error} onRetry={() => void room.refetch()} />
      </>
    )
  }
  if (!room.data || !roomTypes.data || !membership) {
    return (
      <>
        <PageHeader title={t('roomEditor.title', { number: '' })} breadcrumbs={breadcrumbs} />
        <LoadingState variant="rows" />
      </>
    )
  }
  return (
    <RoomEditor
      key={room.data.id}
      room={room.data}
      roomTypes={roomTypes.data}
      amenities={amenities.data ?? []}
      definitions={definitions.data ?? []}
    />
  )
}

function RoomEditor({
  room,
  roomTypes,
  amenities,
  definitions,
}: {
  room: Room
  roomTypes: RoomType[]
  amenities: Amenity[]
  definitions: CustomFieldDefinition[]
}) {
  const { t, i18n } = useTranslation('inventory')
  const lang = i18n.language
  const canEdit = useCan('inventory.manage')
  const invalidate = useInvalidateInventory()
  // a newer server copy (after a save, or housekeeping changing the status) keeps the user's edits
  const { baseline, draft, setDraft, reset, discard } = useServerDraft(draftOf(room), room.updated_at)
  const [tab, setTab] = useState<EditorTab>('attributes')
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({})
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline)

  const category = roomTypes.find((type) => type.id === draft.room_type) ?? roomTypes.find((type) => type.id === room.room_type)
  const categoryName = category ? tr(category.name, lang) : room.room_type_code
  const isDorm = category?.kind === 'dorm'

  const roomFields = definitions.filter((definition) => definition.applies_to === 'room')
  const typeFields = definitions.filter((definition) => definition.applies_to === 'room_type')
  const customTab = roomFields.length > 0 || typeFields.length > 0

  const errors = useMemo(() => validate(draft, category, t), [draft, category, t])
  const hasErrors = Object.keys(errors).length > 0

  const save = useMutation({
    mutationFn: () =>
      api.patch<Room>(`/inventory/rooms/${room.id}/`, {
        number: draft.number,
        name: draft.name,
        floor: draft.floor,
        building: draft.building,
        notes: draft.notes,
        is_active: draft.is_active,
        room_type: draft.room_type,
        overrides: draft.overrides,
        extra_amenities: draft.extra_amenities,
        removed_amenities: draft.removed_amenities,
        custom_values: draft.custom_values,
      }),
    onSuccess: (saved) => {
      toast.success(t('roomEditor.saved'))
      reset(draftOf(saved), saved.updated_at)
      setServerErrors({})
      void invalidate()
    },
    onError: (error) => {
      const fields = isApiError(error) ? flattenFieldErrors(error.fields) : {}
      const first = Object.keys(fields)[0]
      if (!first) {
        toast.error(errorMessage(error, t))
        return
      }
      setServerErrors(fields)
      setTab(tabOfError(first, customTab))
      toast.error(t('roomEditor.checkFields'))
    },
  })

  function patch(changes: Partial<Draft>) {
    setDraft((current) => ({ ...current, ...changes }))
    setServerErrors((current) => withoutErrors(current, Object.keys(changes)))
  }

  function setOverride<K extends OverridableField>(field: K, value: CategoryAttributes[K] | undefined) {
    setDraft((current) => {
      const overrides = { ...current.overrides }
      if (value === undefined) delete overrides[field]
      else overrides[field] = value
      return { ...current, overrides }
    })
    setServerErrors((current) => withoutErrors(current, [`overrides.${field}`]))
  }

  function setCustom(key: string, value: CustomValue | undefined) {
    setDraft((current) => {
      const values = { ...current.custom_values }
      if (value === undefined) delete values[key]
      else values[key] = value
      return { ...current, custom_values: values }
    })
    setServerErrors((current) => withoutErrors(current, [`custom_values.${key}`]))
  }

  const block = room.active_block
  const amenityChanges = draft.extra_amenities.length + draft.removed_amenities.length
  const errorTabs = new Set(Object.keys(serverErrors).map((key) => tabOfError(key, customTab)))
  if (Object.keys(errors).length > 0) errorTabs.add('attributes')
  const amenitiesError = serverErrors.extra_amenities ?? serverErrors.removed_amenities

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: t('nav.rooms'), to: '/app/settings/rooms' }, { label: room.number }]}
        title={
          <span className="flex flex-wrap items-center gap-3">
            <RoomKeyTag number={room.number} status={room.housekeeping_status} inactive={!room.is_active} size="lg" />
            <span>{t('roomEditor.title', { number: room.number })}</span>
          </span>
        }
        description={
          <span className="mt-1 flex flex-wrap items-center gap-2">
            {category && (
              <Link
                to={`/app/settings/room-types/${category.id}`}
                aria-label={t('roomEditor.openCategory', { category: categoryName })}
                className="rounded-md hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
              >
                <CategoryChip code={category.code} name={category.name} color={category.color} />
              </Link>
            )}
            <RoomStatusBadge status={room.housekeeping_status} />
            {block && (
              <Badge tone="stone">
                <Ban aria-hidden />
                {t('roomEditor.blocked', {
                  kind: t(`blockKinds.${block.kind}`),
                  range: formatDateRange(block.start_date, block.end_date, normalizeLang(lang)),
                })}
              </Badge>
            )}
            {!room.is_active && <Badge tone="stone">{t('common.inactive')}</Badge>}
          </span>
        }
      />

      <Tabs value={tab} onValueChange={(value) => setTab(value as EditorTab)}>
        <TabsList aria-label={t('roomEditor.sections')}>
          <TabsTrigger value="attributes">
            {t('roomEditor.tabs.attributes')}
            {errorTabs.has('attributes') && <TabErrorDot />}
          </TabsTrigger>
          <TabsTrigger value="amenities">
            {t('roomEditor.tabs.amenities')}
            {amenityChanges > 0 && <span className="num rounded-full bg-accent-soft px-1.5 text-2xs text-accent-ink">{amenityChanges}</span>}
            {errorTabs.has('amenities') && <TabErrorDot />}
          </TabsTrigger>
          {customTab && (
            <TabsTrigger value="custom">
              {t('roomEditor.tabs.custom')}
              {errorTabs.has('custom') && <TabErrorDot />}
            </TabsTrigger>
          )}
          {isDorm && <TabsTrigger value="beds">{t('roomEditor.tabs.beds')}</TabsTrigger>}
          <TabsTrigger value="blocks">{t('roomEditor.tabs.blocks')}</TabsTrigger>
        </TabsList>

        <TabsContent value="attributes" className="grid gap-8">
          <OwnFields
            draft={draft}
            roomTypes={roomTypes}
            patch={patch}
            canEdit={canEdit}
            changedType={draft.room_type !== room.room_type}
            errors={{ ...serverErrors, ...(errors.number ? { number: errors.number } : {}) }}
          />

          <section aria-labelledby="inherited-heading" className="grid gap-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="inherited-heading" className="text-[15px] text-fg">
                {t('roomEditor.inheritedTitle')}
              </h2>
              <p className="text-xs text-muted">
                {t('roomEditor.overriddenCount', { count: Object.keys(draft.overrides).length, category: categoryName })}
              </p>
            </div>
            <div className="rounded-lg border border-border bg-surface px-4 py-1 shadow-xs">
              <div className="divide-y divide-border/70">
                {OVERRIDABLE_FIELDS.map((field) => (
                  <AttributeRow
                    key={field}
                    field={field}
                    draft={draft}
                    category={category}
                    categoryName={categoryName}
                    setOverride={setOverride}
                    error={errors[field] ?? serverErrors[`overrides.${field}`]}
                    locked={!canEdit || (isDorm && (OCCUPANCY_FIELDS as readonly string[]).includes(field))}
                    lockedHint={isDorm && canEdit ? t('roomEditor.dormOccupancy') : undefined}
                  />
                ))}
              </div>
            </div>
          </section>
        </TabsContent>

        <TabsContent value="amenities" className="grid gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="max-w-xl text-sm text-muted">{t('roomEditor.amenitiesHint', { category: categoryName })}</p>
            {canEdit && amenityChanges > 0 && (
              <Button variant="ghost" size="sm" onClick={() => patch({ extra_amenities: [], removed_amenities: [] })}>
                <RotateCcw aria-hidden />
                {t('common.restore')}
              </Button>
            )}
          </div>
          {amenitiesError && (
            <p role="alert" className="text-xs font-medium text-danger-ink">
              {amenitiesError}
            </p>
          )}
          <fieldset disabled={!canEdit} className="contents">
            <AmenityPicker
              mode="inherit"
              amenities={amenities}
              inherited={category?.amenities ?? []}
              extra={draft.extra_amenities}
              removed={draft.removed_amenities}
              onChange={({ extra, removed }) => patch({ extra_amenities: extra, removed_amenities: removed })}
            />
          </fieldset>
        </TabsContent>

        <TabsContent value="custom" className="grid gap-6">
          {roomFields.length > 0 && (
            <section className="grid gap-2" aria-labelledby="room-fields-heading">
              <h2 id="room-fields-heading" className="text-[15px] text-fg">
                {t('roomEditor.roomFields')}
              </h2>
              <div className="divide-y divide-border/70 rounded-lg border border-border bg-surface px-4 shadow-xs">
                {roomFields.map((definition) => (
                  <CustomRow key={definition.id} definition={definition} error={serverErrors[`custom_values.${definition.key}`]}>
                    {(labelId) =>
                      canEdit ? (
                        <CustomFieldInput
                          definition={definition}
                          labelledBy={labelId}
                          value={draft.custom_values[definition.key] ?? definition.default_value ?? undefined}
                          onChange={(value) => setCustom(definition.key, value)}
                        />
                      ) : (
                        <span className="text-muted">{customValueText(definition, draft.custom_values[definition.key], lang, t)}</span>
                      )
                    }
                  </CustomRow>
                ))}
              </div>
            </section>
          )}
          {typeFields.length > 0 && (
            <section className="grid gap-2" aria-labelledby="type-fields-heading">
              <h2 id="type-fields-heading" className="text-[15px] text-fg">
                {t('roomEditor.categoryFields', { category: categoryName })}
              </h2>
              <div className="divide-y divide-border/70 rounded-lg border border-border bg-surface px-4 py-1 shadow-xs">
                {typeFields.map((definition) => {
                  const inherited = category?.custom_values?.[definition.key]
                  const overridden = definition.key in draft.custom_values
                  return (
                    <InheritedField
                      key={definition.id}
                      label={tr(definition.label, lang)}
                      categoryName={categoryName}
                      overridden={overridden}
                      inheritedText={customValueText(definition, inherited, lang, t)}
                      locked={!canEdit}
                      error={serverErrors[`custom_values.${definition.key}`]}
                      onOverride={() => setCustom(definition.key, inherited ?? definition.default_value ?? null)}
                      onRestore={() => setCustom(definition.key, undefined)}
                      control={(labelId) => (
                        <CustomFieldInput
                          definition={definition}
                          labelledBy={labelId}
                          value={draft.custom_values[definition.key]}
                          onChange={(value) => setCustom(definition.key, value)}
                        />
                      )}
                    />
                  )
                })}
              </div>
            </section>
          )}
        </TabsContent>

        {isDorm && (
          <TabsContent value="beds">
            <RoomBedsPanel room={room} canEdit={canEdit} />
          </TabsContent>
        )}

        <TabsContent value="blocks">
          <RoomBlocksPanel room={room} canEdit={canEdit} />
        </TabsContent>
      </Tabs>

      <SaveBar
        visible={canEdit && dirty}
        saving={save.isPending}
        disabled={hasErrors}
        problem={hasErrors ? t('roomEditor.fixErrors') : undefined}
        onSave={() => save.mutate()}
        onDiscard={discard}
      />
    </>
  )
}

function validate(draft: Draft, category: RoomType | undefined, t: ReturnType<typeof useTranslation>['t']) {
  const errors: Partial<Record<OverridableField | 'number', string>> = {}
  if (!draft.number.trim()) errors.number = t('common:validation.required')
  if (!category) return errors
  for (const field of NUMBER_FIELDS) {
    if (field in draft.overrides && !Number.isFinite(draft.overrides[field] as number)) {
      errors[field] = t('common:validation.number')
    }
  }
  if ('size_m2' in draft.overrides) {
    const size = Number(draft.overrides.size_m2)
    if (!draft.overrides.size_m2 || !Number.isFinite(size) || size <= 0) errors.size_m2 = t('common:validation.number')
  }
  if ('name' in draft.overrides && !tr(draft.overrides.name, 'es') && !tr(draft.overrides.name, 'en')) {
    errors.name = t('common:validation.required')
  }
  if (category.kind === 'dorm') return errors
  const occupancy = Object.fromEntries(
    OCCUPANCY_FIELDS.map((field) => [field, field in draft.overrides ? (draft.overrides[field] as number) : category[field]]),
  ) as Record<OccupancyField, number>
  const overriddenOccupancy = OCCUPANCY_FIELDS.filter((field) => field in draft.overrides)
  for (const [field, message] of Object.entries(occupancyErrors(occupancy, t)) as [OccupancyField, string][]) {
    // show it on a field the room overrides (the category values are consistent on their own)
    const target = field in draft.overrides ? field : (overriddenOccupancy.includes('max_occupancy') ? 'max_occupancy' : overriddenOccupancy[0])
    if (target && !errors[target]) errors[target] = message
  }
  return errors
}

type EditorTab = 'attributes' | 'amenities' | 'custom' | 'beds' | 'blocks'

/** The tab that shows the field of a server error key (`custom_values.x`, `overrides.x`, `number`…). */
function tabOfError(key: string, customTab: boolean): EditorTab {
  if (key.startsWith('custom_values.') && customTab) return 'custom'
  if (key.startsWith('extra_amenities') || key.startsWith('removed_amenities')) return 'amenities'
  return 'attributes'
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null
  return (
    <span id={id} className="text-xs font-medium text-danger-ink" aria-live="polite">
      {message}
    </span>
  )
}

type OwnFieldKey = 'number' | 'floor' | 'building' | 'name' | 'notes'

function OwnFields({
  draft,
  roomTypes,
  patch,
  canEdit,
  changedType,
  errors,
}: {
  draft: Draft
  roomTypes: RoomType[]
  patch: (changes: Partial<Draft>) => void
  canEdit: boolean
  changedType: boolean
  errors: Record<string, string>
}) {
  const { t, i18n } = useTranslation('inventory')
  const ids = { number: useId(), name: useId(), floor: useId(), building: useId(), type: useId(), notes: useId() }
  const invalid = (key: OwnFieldKey, id: string) =>
    errors[key] ? { 'aria-invalid': true, 'aria-describedby': `${id}-error` } : {}
  return (
    <section aria-labelledby="own-heading" className="grid gap-3">
      <h2 id="own-heading" className="text-[15px] text-fg">
        {t('roomEditor.ownTitle')}
      </h2>
      <fieldset disabled={!canEdit} className="grid gap-4 rounded-lg border border-border bg-surface p-4 shadow-xs sm:grid-cols-2 lg:grid-cols-4">
        <label className="grid content-start gap-1.5" htmlFor={ids.number}>
          <span className="text-[13px] font-semibold">{t('fields.number')}</span>
          <Input id={ids.number} name="number" value={draft.number} maxLength={20} {...invalid('number', ids.number)} onChange={(event) => patch({ number: event.target.value })} />
          <FieldError id={`${ids.number}-error`} message={errors.number} />
        </label>
        <label className="grid content-start gap-1.5" htmlFor={ids.floor}>
          <span className="text-[13px] font-semibold">{t('fields.floor')}</span>
          <Input id={ids.floor} name="floor" value={draft.floor} maxLength={20} {...invalid('floor', ids.floor)} onChange={(event) => patch({ floor: event.target.value })} />
          <FieldError id={`${ids.floor}-error`} message={errors.floor} />
        </label>
        <label className="grid content-start gap-1.5" htmlFor={ids.building}>
          <span className="text-[13px] font-semibold">{t('fields.building')}</span>
          <Input id={ids.building} name="building" value={draft.building} maxLength={50} {...invalid('building', ids.building)} onChange={(event) => patch({ building: event.target.value })} />
          <FieldError id={`${ids.building}-error`} message={errors.building} />
        </label>
        <label className="grid content-start gap-1.5" htmlFor={ids.name}>
          <span className="text-[13px] font-semibold">{t('fields.roomName')}</span>
          <Input id={ids.name} name="name" value={draft.name} maxLength={100} placeholder={t('roomEditor.roomNamePlaceholder')} {...invalid('name', ids.name)} onChange={(event) => patch({ name: event.target.value })} />
          <FieldError id={`${ids.name}-error`} message={errors.name} />
        </label>
        <div className="grid content-start gap-1.5 sm:col-span-2">
          <span id={ids.type} className="text-[13px] font-semibold">
            {t('fields.room_type')}
          </span>
          <Select name="room_type" value={draft.room_type} onValueChange={(value) => patch({ room_type: value })} disabled={!canEdit}>
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
          {changedType && <p className="text-xs text-warning-ink">{t('roomEditor.changeTypeHint')}</p>}
          <FieldError id={`${ids.type}-error`} message={errors.room_type} />
        </div>
        <label className="grid content-start gap-1.5 sm:col-span-2" htmlFor={ids.notes}>
          <span className="text-[13px] font-semibold">{t('fields.notes')}</span>
          <Textarea id={ids.notes} name="notes" rows={2} value={draft.notes} {...invalid('notes', ids.notes)} onChange={(event) => patch({ notes: event.target.value })} />
          <FieldError id={`${ids.notes}-error`} message={errors.notes} />
        </label>
        <label className="flex items-center gap-3 sm:col-span-2 lg:col-span-4">
          <Switch name="is_active" checked={draft.is_active} onCheckedChange={(checked) => patch({ is_active: checked })} />
          <span className="grid">
            <span className="text-[13px] font-semibold">{t('fields.is_active')}</span>
            <span className="text-xs text-muted">{t('roomEditor.activeHint')}</span>
          </span>
        </label>
      </fieldset>
    </section>
  )
}

function AttributeRow({
  field,
  draft,
  category,
  categoryName,
  setOverride,
  error,
  locked,
  lockedHint,
}: {
  field: OverridableField
  draft: Draft
  category: RoomType | undefined
  categoryName: string
  setOverride: <K extends OverridableField>(field: K, value: CategoryAttributes[K] | undefined) => void
  error?: string
  locked: boolean
  lockedHint?: string
}) {
  const { t, i18n } = useTranslation('inventory')
  const lang = i18n.language
  const label = t(`fields.${field}`)
  const inherited = category?.[field]
  const overridden = field in draft.overrides
  const value = draft.overrides[field]

  function control(labelId: string) {
    switch (field) {
      case 'name':
      case 'description':
        return (
          <I18nTextInput
            name={`overrides.${field}`}
            label={label}
            multiline={field === 'description'}
            value={(value as CategoryAttributes['name']) ?? {}}
            invalid={Boolean(error)}
            onChange={(next) => setOverride(field, next)}
          />
        )
      case 'beds':
        return <BedConfigEditor name="overrides.beds" labelledBy={labelId} value={(value as CategoryAttributes['beds']) ?? []} onChange={(next) => setOverride('beds', next)} />
      case 'view':
        return <ViewSelect name="overrides.view" labelledBy={labelId} value={(value as string) ?? ''} onChange={(next) => setOverride('view', next)} />
      case 'smoking_allowed':
      case 'accessible':
        return <Switch name={`overrides.${field}`} aria-labelledby={labelId} checked={Boolean(value)} onCheckedChange={(checked) => setOverride(field, checked)} />
      case 'size_m2':
        return (
          <Input
            type="number"
            name="overrides.size_m2"
            aria-labelledby={labelId}
            aria-invalid={Boolean(error)}
            min={1}
            step="0.5"
            className="w-full sm:w-40"
            value={(value as string) ?? ''}
            onChange={(event) => setOverride('size_m2', event.target.value)}
          />
        )
      default:
        return (
          <Input
            type="number"
            name={`overrides.${field}`}
            aria-labelledby={labelId}
            aria-invalid={Boolean(error)}
            min={field === 'max_children' ? 0 : 1}
            className="w-full sm:w-40"
            value={Number.isFinite(value as number) ? String(value) : ''}
            onChange={(event) => setOverride(field, event.target.valueAsNumber as never)}
          />
        )
    }
  }

  return (
    <InheritedField
      label={label}
      categoryName={categoryName}
      overridden={overridden}
      inheritedText={attributeText(field, inherited, t, lang)}
      locked={locked}
      lockedHint={lockedHint}
      error={error}
      control={control}
      onOverride={() => setOverride(field, structuredClone(inherited) as never)}
      onRestore={() => setOverride(field, undefined)}
    />
  )
}

function CustomRow({
  definition,
  error,
  children,
}: {
  definition: CustomFieldDefinition
  error?: string
  children: (labelId: string) => React.ReactNode
}) {
  const { i18n } = useTranslation('inventory')
  const labelId = useId()
  return (
    <div
      role="group"
      aria-labelledby={labelId}
      aria-describedby={error ? `${labelId}-error` : undefined}
      className="grid gap-2 py-3 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)] sm:items-center"
    >
      <span id={labelId} className="text-[13px] font-semibold">
        {tr(definition.label, i18n.language)}
        {definition.required && <span className="text-accent-ink"> *</span>}
      </span>
      <div className="grid gap-1">
        {children(labelId)}
        <FieldError id={`${labelId}-error`} message={error} />
      </div>
    </div>
  )
}
