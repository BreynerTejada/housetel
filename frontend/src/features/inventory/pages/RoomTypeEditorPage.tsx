import { useMutation } from '@tanstack/react-query'
import { BedDouble, Copy, Trash2, Users } from 'lucide-react'
import { useId, useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api, isApiError } from '@/lib/api'
import { useActiveMembership } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  useAmenities,
  useCustomFields,
  useInvalidateInventory,
  useRoomType,
  type BedConfig,
  type CustomValues,
  type I18nText,
  type RoomType,
  type RoomTypeKind,
} from '../api'
import { AmenityCreateDialog } from '../components/AmenityCreateDialog'
import { AmenityPicker } from '../components/AmenityPicker'
import { BedConfigEditor } from '../components/BedConfigEditor'
import { CustomFieldInput } from '../components/CustomFieldInput'
import { I18nTextInput } from '../components/I18nTextInput'
import { PhotoGallery } from '../components/PhotoGallery'
import { SaveBar } from '../components/SaveBar'
import { TabErrorDot } from '../components/TabErrorDot'
import { ViewSelect } from '../components/ViewSelect'
import { OCCUPANCY_FIELDS, occupancyErrors, type OccupancyField } from '../lib/attributes'
import { flattenFieldErrors, withoutErrors } from '../lib/fieldErrors'
import { tr } from '../lib/text'
import { useServerDraft } from '../lib/useServerDraft'

/** Warm-Nordic palette for categories (the room-state colors and a few neighbors). */
const SWATCHES = ['#4E6C88', '#5F7F66', '#B4583B', '#B98A2E', '#8C857B', '#6B5B95', '#2F6F73', '#A0524D']

interface TypeDraft {
  code: string
  name: I18nText
  description: I18nText
  kind: RoomTypeKind
  base_occupancy: number
  max_adults: number
  max_children: number
  max_occupancy: number
  beds: BedConfig[]
  size_m2: string
  view: string
  smoking_allowed: boolean
  accessible: boolean
  amenities: string[]
  color: string
  housekeeping_minutes: number
  is_active: boolean
  custom_values: CustomValues
}

const NEW_TYPE: TypeDraft = {
  code: '',
  name: {},
  description: {},
  kind: 'private',
  base_occupancy: 2,
  max_adults: 2,
  max_children: 0,
  max_occupancy: 2,
  beds: [{ type: 'double', count: 1 }],
  size_m2: '',
  view: '',
  smoking_allowed: false,
  accessible: false,
  amenities: [],
  color: SWATCHES[0] ?? '#4E6C88',
  housekeeping_minutes: 30,
  is_active: true,
  custom_values: {},
}

function draftOf(type: RoomType): TypeDraft {
  return {
    code: type.code,
    name: { ...type.name },
    description: { ...type.description },
    kind: type.kind,
    base_occupancy: type.base_occupancy,
    max_adults: type.max_adults,
    max_children: type.max_children,
    max_occupancy: type.max_occupancy,
    beds: type.beds.map((bed) => ({ ...bed })),
    size_m2: type.size_m2 ?? '',
    view: type.view,
    smoking_allowed: type.smoking_allowed,
    accessible: type.accessible,
    amenities: [...type.amenities],
    color: type.color,
    housekeeping_minutes: type.housekeeping_minutes,
    is_active: type.is_active,
    custom_values: { ...type.custom_values },
  }
}

export default function RoomTypeEditorPage() {
  const { roomTypeId } = useParams()
  const { t } = useTranslation('inventory')
  const isNew = roomTypeId === 'new'
  const roomType = useRoomType(isNew ? undefined : roomTypeId)
  const membership = useActiveMembership()
  const breadcrumbs = [{ label: t('nav.roomTypes'), to: '/app/settings/room-types' }, { label: isNew ? t('roomTypes.new') : (roomType.data?.code ?? '…') }]

  if (roomType.isError) {
    return (
      <>
        <PageHeader title={t('roomTypes.editTitle')} breadcrumbs={breadcrumbs} />
        <ErrorState error={roomType.error} onRetry={() => void roomType.refetch()} />
      </>
    )
  }
  if ((!isNew && !roomType.data) || !membership) {
    return (
      <>
        <PageHeader title={t('roomTypes.editTitle')} breadcrumbs={breadcrumbs} />
        <LoadingState variant="rows" />
      </>
    )
  }
  return <RoomTypeEditor key={roomType.data?.id ?? 'new'} roomType={roomType.data ?? null} breadcrumbs={breadcrumbs} />
}

function RoomTypeEditor({ roomType, breadcrumbs }: { roomType: RoomType | null; breadcrumbs: { label: string; to?: string }[] }) {
  const { t, i18n } = useTranslation('inventory')
  const navigate = useNavigate()
  const canEdit = useCan('inventory.manage')
  const invalidate = useInvalidateInventory()
  const amenities = useAmenities()
  const definitions = useCustomFields('room_type')
  // a newer server copy (the refetch after a save, another admin's change) keeps the user's edits
  const { baseline, draft, setDraft, reset, discard } = useServerDraft<TypeDraft>(
    roomType ? draftOf(roomType) : NEW_TYPE,
    roomType?.updated_at ?? 'new',
  )
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({})
  const [tab, setTab] = useState<TypeTab>('general')
  const isNew = roomType === null
  const dirty = isNew || JSON.stringify(draft) !== JSON.stringify(baseline)
  const hasRooms = (roomType?.rooms_count ?? 0) > 0

  const errors = useMemo(() => {
    const found: Partial<Record<OccupancyField | 'name' | 'size_m2' | 'housekeeping_minutes', string>> = {}
    if (!draft.name.es?.trim() && !draft.name.en?.trim()) found.name = t('common:validation.required')
    if (draft.size_m2 && !(Number(draft.size_m2) > 0)) found.size_m2 = t('common:validation.number')
    if (!(draft.housekeeping_minutes >= 5 && draft.housekeeping_minutes <= 480)) found.housekeeping_minutes = t('roomTypes.minutesRange')
    if (draft.kind === 'private') {
      for (const field of OCCUPANCY_FIELDS) {
        if (!Number.isFinite(draft[field])) found[field] = t('common:validation.number')
      }
      Object.assign(found, occupancyErrors(draft, t), found)
    }
    return found
  }, [draft, t])
  const hasErrors = Object.keys(errors).length > 0

  function patch(changes: Partial<TypeDraft>) {
    setDraft((current) => ({ ...current, ...changes }))
    setServerErrors((current) => withoutErrors(current, Object.keys(changes)))
  }

  const save = useMutation({
    mutationFn: () => {
      const body = { ...draft, size_m2: draft.size_m2 || null }
      return isNew ? api.post<RoomType>('/inventory/room-types/', body) : api.patch<RoomType>(`/inventory/room-types/${roomType.id}/`, body)
    },
    onSuccess: (saved) => {
      toast.success(isNew ? t('roomTypes.created') : t('roomTypes.saved'))
      void invalidate()
      if (isNew) {
        navigate(`/app/settings/room-types/${saved.id}`, { replace: true })
      } else {
        reset(draftOf(saved), saved.updated_at)
      }
    },
    onError: (error) => {
      const fields = isApiError(error) ? flattenFieldErrors(error.fields) : {}
      const first = Object.keys(fields)[0]
      setServerErrors(fields)
      if (first) setTab(tabOfError(first))
      toast.error(first ? t('roomEditor.checkFields') : errorMessage(error, t))
    },
  })

  const duplicate = useMutation({
    mutationFn: () => api.post<RoomType>(`/inventory/room-types/${roomType?.id}/duplicate/`, {}),
    onSuccess: (copy) => {
      toast.success(t('roomTypes.duplicated', { code: copy.code }))
      void invalidate()
      navigate(`/app/settings/room-types/${copy.id}`)
    },
    onError: (error) => toast.error(errorMessage(error, t)),
  })

  const remove = useMutation({
    mutationFn: () => api.delete(`/inventory/room-types/${roomType?.id}/`),
    onSuccess: () => {
      toast.success(t('roomTypes.deleted'))
      void invalidate()
      navigate('/app/settings/room-types')
    },
  })

  const errorOf = (field: string) => serverErrors[field] ?? errors[field as keyof typeof errors]
  const errorTabs = new Set([...Object.keys(serverErrors), ...Object.keys(errors)].map(tabOfError))
  const title = isNew ? t('roomTypes.new') : tr(roomType.name, i18n.language) || roomType.code

  return (
    <>
      <PageHeader
        breadcrumbs={breadcrumbs}
        title={
          <span className="flex items-center gap-3">
            <span aria-hidden className="size-4 rounded-[5px] ring-1 ring-black/5" style={{ backgroundColor: draft.color }} />
            {title}
          </span>
        }
        description={
          isNew ? (
            t('roomTypes.newDescription')
          ) : (
            <span className="flex flex-wrap items-baseline gap-x-2">
              {t('roomTypes.editDescription', { count: roomType.rooms_count })}
              {hasRooms && (
                <Link to={`/app/settings/rooms?room_type=${roomType.id}`} className="font-semibold text-accent-ink hover:underline">
                  {t('roomTypes.viewRooms', { count: roomType.rooms_count })}
                </Link>
              )}
            </span>
          )
        }
        actions={
          !isNew &&
          canEdit && (
            <>
              <Button onClick={() => duplicate.mutate()} loading={duplicate.isPending}>
                <Copy aria-hidden />
                {t('roomTypes.duplicate')}
              </Button>
              <ConfirmDialog
                title={t('roomTypes.deleteTitle', { name: title })}
                description={hasRooms ? t('roomTypes.deleteWithRooms') : t('roomTypes.deleteDescription')}
                confirmLabel={t('common:actions.delete')}
                onConfirm={() => remove.mutateAsync()}
                trigger={
                  <Button variant="ghost" aria-label={t('roomTypes.delete')}>
                    <Trash2 aria-hidden />
                  </Button>
                }
              />
            </>
          )
        }
      />

      <Tabs value={tab} onValueChange={(value) => setTab(value as TypeTab)}>
        <TabsList aria-label={t('roomTypes.sections')}>
          {(['general', 'capacity', 'amenities', 'photos'] as const).map((value) => (
            <TabsTrigger key={value} value={value}>
              {t(`roomTypes.tabs.${value}`)}
              {errorTabs.has(value) && <TabErrorDot />}
            </TabsTrigger>
          ))}
          {(definitions.data?.length ?? 0) > 0 && (
            <TabsTrigger value="custom">
              {t('roomTypes.tabs.custom')}
              {errorTabs.has('custom') && <TabErrorDot />}
            </TabsTrigger>
          )}
        </TabsList>

        <fieldset disabled={!canEdit} className="contents">
          <TabsContent value="general" className="grid gap-5">
            <Section title={t('roomTypes.identity')}>
              <FieldRow label={t('fields.name')} error={errorOf('name')} group>
                {() => <I18nTextInput label={t('fields.name')} name="name" value={draft.name} invalid={Boolean(errorOf('name'))} onChange={(name) => patch({ name })} />}
              </FieldRow>
              <FieldRow label={t('fields.code')} hint={t('roomTypes.codeHint')} error={errorOf('code')}>
                {(id) => (
                  <Input id={id} name="code" className="w-40 uppercase num" maxLength={20} placeholder={t('roomTypes.codeAuto')}
                         value={draft.code} onChange={(event) => patch({ code: event.target.value.toUpperCase() })} />
                )}
              </FieldRow>
              <FieldRow label={t('fields.description')} group>
                {() => <I18nTextInput label={t('fields.description')} name="description" multiline value={draft.description} onChange={(description) => patch({ description })} />}
              </FieldRow>
            </Section>

            <Section title={t('fields.kind')} description={hasRooms ? t('roomTypes.kindLocked') : undefined}>
              <RadioGroup
                value={draft.kind}
                onValueChange={(kind) => patch({ kind: kind as RoomTypeKind })}
                disabled={hasRooms || !canEdit}
                aria-label={t('fields.kind')}
                className="grid gap-3 sm:grid-cols-2"
              >
                {(['private', 'dorm'] as const).map((kind) => (
                  <label
                    key={kind}
                    className={cn(
                      'flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-surface p-4 transition-colors',
                      draft.kind === kind && 'border-accent bg-accent-soft/40',
                      (hasRooms || !canEdit) && 'cursor-not-allowed opacity-70',
                    )}
                  >
                    <RadioGroupItem value={kind} className="mt-0.5" />
                    <span className="grid gap-1">
                      <span className="flex items-center gap-2 font-semibold text-fg">
                        {kind === 'private' ? <BedDouble aria-hidden className="size-4" /> : <Users aria-hidden className="size-4" />}
                        {t(`common.kind.${kind}`)}
                      </span>
                      <span className="text-[13px] text-muted">{t(`roomTypes.kindHint.${kind}`)}</span>
                    </span>
                  </label>
                ))}
              </RadioGroup>
            </Section>

            <Section title={t('roomTypes.details')}>
              <FieldRow label={t('fields.color')} group>
                {() => (
                  <div role="radiogroup" aria-label={t('fields.color')} className="flex flex-wrap gap-2">
                    {SWATCHES.map((color) => (
                      <button
                        key={color}
                        type="button"
                        role="radio"
                        aria-checked={draft.color.toLowerCase() === color.toLowerCase()}
                        aria-label={color}
                        onClick={() => patch({ color })}
                        className={cn(
                          'size-8 rounded-md ring-offset-2 ring-offset-bg transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                          draft.color.toLowerCase() === color.toLowerCase() && 'ring-2 ring-fg',
                        )}
                        style={{ backgroundColor: color }}
                      />
                    ))}
                  </div>
                )}
              </FieldRow>
              <FieldRow label={t('fields.view')}>{(id) => <ViewSelect id={id} name="view" value={draft.view} onChange={(view) => patch({ view })} />}</FieldRow>
              <FieldRow label={t('fields.size_m2')} error={errorOf('size_m2')}>
                {(id) => (
                  <Input id={id} name="size_m2" type="number" min={1} step="0.5" className="w-32" value={draft.size_m2}
                         aria-invalid={Boolean(errorOf('size_m2'))} onChange={(event) => patch({ size_m2: event.target.value })} />
                )}
              </FieldRow>
              <FieldRow label={t('fields.housekeeping_minutes')} hint={t('roomTypes.minutesHint')} error={errorOf('housekeeping_minutes')}>
                {(id) => (
                  <Input id={id} name="housekeeping_minutes" type="number" min={5} max={480} className="w-32"
                         value={Number.isFinite(draft.housekeeping_minutes) ? String(draft.housekeeping_minutes) : ''}
                         onChange={(event) => patch({ housekeeping_minutes: event.target.valueAsNumber })} />
                )}
              </FieldRow>
              <SwitchRow name="accessible" label={t('fields.accessible')} checked={draft.accessible} onChange={(accessible) => patch({ accessible })} />
              <SwitchRow name="smoking_allowed" label={t('fields.smoking_allowed')} checked={draft.smoking_allowed} onChange={(smoking_allowed) => patch({ smoking_allowed })} />
              <SwitchRow name="is_active" label={t('fields.is_active')} hint={t('roomTypes.activeHint')} checked={draft.is_active} onChange={(is_active) => patch({ is_active })} />
            </Section>
          </TabsContent>

          <TabsContent value="capacity" className="grid gap-5">
            <Section title={t('roomTypes.occupancy')} description={draft.kind === 'private' ? t('roomTypes.occupancyHint') : undefined}>
              {draft.kind === 'dorm' ? (
                <p className="rounded-lg border border-dashed border-border-strong bg-surface-2/50 p-4 text-sm text-muted">{t('roomTypes.dormOccupancy')}</p>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {OCCUPANCY_FIELDS.map((field) => (
                    <FieldRow key={field} label={t(`fields.${field}`)} error={errorOf(field)} stacked>
                      {(id) => (
                        <Input id={id} name={field} type="number" min={field === 'max_children' ? 0 : 1} max={20}
                               aria-invalid={Boolean(errorOf(field))}
                               value={Number.isFinite(draft[field]) ? String(draft[field]) : ''}
                               onChange={(event) => patch({ [field]: event.target.valueAsNumber } as Partial<TypeDraft>)} />
                      )}
                    </FieldRow>
                  ))}
                </div>
              )}
            </Section>
            <Section title={t('fields.beds')} description={t(draft.kind === 'dorm' ? 'roomTypes.bedsHintDorm' : 'roomTypes.bedsHint')}>
              <BedConfigEditor value={draft.beds} onChange={(beds) => patch({ beds })} />
            </Section>
          </TabsContent>

          <TabsContent value="amenities" className="grid gap-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="max-w-xl text-sm text-muted">{t('roomTypes.amenitiesHint')}</p>
              {canEdit && <AmenityCreateDialog onCreated={(amenity) => patch({ amenities: [...draft.amenities, amenity.code] })} />}
            </div>
            {amenities.data ? (
              <AmenityPicker mode="select" amenities={amenities.data} value={draft.amenities} onChange={(value) => patch({ amenities: value })} />
            ) : (
              <LoadingState variant="rows" rows={3} />
            )}
          </TabsContent>

          <TabsContent value="custom" className="grid gap-2">
            <div className="divide-y divide-border/70 rounded-lg border border-border bg-surface px-4 shadow-xs">
              {(definitions.data ?? []).map((definition) => (
                <FieldRow key={definition.id} label={tr(definition.label, i18n.language)} error={serverErrors[`custom_values.${definition.key}`]}>
                  {(id) => (
                    <CustomFieldInput
                      id={id}
                      definition={definition}
                      value={draft.custom_values[definition.key] ?? definition.default_value ?? undefined}
                      onChange={(value) => patch({ custom_values: { ...draft.custom_values, [definition.key]: value } })}
                    />
                  )}
                </FieldRow>
              ))}
            </div>
          </TabsContent>
        </fieldset>

        <TabsContent value="photos">
          {isNew ? (
            <p className="rounded-lg border border-dashed border-border-strong p-6 text-center text-sm text-muted">{t('photos.saveFirst')}</p>
          ) : (
            <PhotoGallery roomTypeId={roomType.id} canEdit={canEdit} label={t('photos.categoryPhotos')} />
          )}
        </TabsContent>
      </Tabs>

      <SaveBar
        visible={canEdit && dirty}
        saving={save.isPending}
        disabled={hasErrors}
        problem={hasErrors ? t('roomEditor.fixErrors') : undefined}
        saveLabel={isNew ? t('roomTypes.create') : undefined}
        onSave={() => save.mutate()}
        onDiscard={isNew ? undefined : discard}
      />
    </>
  )
}

type TypeTab = 'general' | 'capacity' | 'amenities' | 'photos' | 'custom'

const CAPACITY_KEYS = [...OCCUPANCY_FIELDS, 'beds']

/** The tab that shows the field of an error key (`max_adults`, `beds.0.count`, `custom_values.x`…). */
function tabOfError(key: string): TypeTab {
  const field = key.split('.')[0] ?? key
  if (field === 'custom_values') return 'custom'
  if (field === 'amenities') return 'amenities'
  if (CAPACITY_KEYS.includes(field)) return 'capacity'
  return 'general'
}

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="grid gap-3">
      <div>
        <h2 className="text-[15px] text-fg">{title}</h2>
        {description && <p className="mt-0.5 text-[13px] text-muted">{description}</p>}
      </div>
      <div className="grid gap-4 rounded-lg border border-border bg-surface p-4 shadow-xs">{children}</div>
    </section>
  )
}

function FieldRow({ label, hint, error, stacked, group, children }: {
  label: string
  hint?: string
  error?: string
  stacked?: boolean
  /** The control is several inputs with their own labels (bilingual text, swatches): label a group instead. */
  group?: boolean
  children: (id: string) => ReactNode
}) {
  const id = useId()
  const labelClass = 'pt-2 text-[13px] font-semibold text-fg'
  return (
    <div
      role={group ? 'group' : undefined}
      aria-labelledby={group ? `${id}-label` : undefined}
      className={cn('grid gap-1.5', !stacked && 'sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)] sm:items-start sm:gap-4')}
    >
      {group ? (
        <span id={`${id}-label`} className={labelClass}>
          {label}
        </span>
      ) : (
        <label htmlFor={id} className={labelClass}>
          {label}
        </label>
      )}
      <div className="grid gap-1">
        {children(id)}
        {hint && <p className="text-xs text-muted">{hint}</p>}
        {error && (
          <p className="text-xs font-medium text-danger-ink" aria-live="polite">
            {error}
          </p>
        )}
      </div>
    </div>
  )
}

function SwitchRow({ name, label, hint, checked, onChange }: {
  name: string
  label: string
  hint?: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex items-center gap-3">
      <Switch checked={checked} onCheckedChange={onChange} name={name} />
      <span className="grid">
        <span className="text-[13px] font-semibold">{label}</span>
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </span>
    </label>
  )
}
