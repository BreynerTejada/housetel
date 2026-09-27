import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import { arrayMove, rectSortingStrategy, SortableContext, sortableKeyboardCoordinates, useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useMutation } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, GripVertical, ImagePlus, PencilLine, Trash2 } from 'lucide-react'
import { useId, useState, type DragEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { photosPath, useInvalidateInventory, usePhotos, type I18nText, type Photo } from '../api'
import { tr } from '../lib/text'
import { I18nTextInput } from './I18nTextInput'

const ACCEPT = 'image/jpeg,image/png,image/webp'

/**
 * Photos of a category (`roomTypeId`) or of the property (`null`). They are public: the marketplace and the
 * booking engine show them. Drag to reorder (the first one is the cover) or use the move buttons.
 */
export function PhotoGallery({ roomTypeId, canEdit, label }: { roomTypeId: string | null; canEdit: boolean; label: string }) {
  const { t, i18n } = useTranslation('inventory')
  const photos = usePhotos(roomTypeId)
  const invalidate = useInvalidateInventory()
  const inputId = useId()
  const [order, setOrder] = useState<string[] | null>(null)
  const [uploading, setUploading] = useState<{ done: number; total: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  const [editing, setEditing] = useState<Photo | null>(null)
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const reorder = useMutation({
    mutationFn: (ids: string[]) => api.post<Photo[]>(`${photosPath(roomTypeId)}reorder/`, { ids }),
    onSuccess: () => {
      toast.success(t('photos.reordered'))
      void invalidate()
    },
    onError: (error) => {
      setOrder(null)
      toast.error(errorMessage(error, t))
    },
  })
  const remove = useMutation({
    mutationFn: (photo: Photo) => api.delete(`${photosPath(roomTypeId)}${photo.id}/`),
    onSuccess: () => {
      toast.success(t('photos.deleted'))
      setOrder(null)
      void invalidate()
    },
  })

  async function upload(files: FileList | File[]) {
    const images = [...files].filter((file) => ACCEPT.split(',').includes(file.type))
    if (!images.length) {
      toast.error(t('photos.wrongType'))
      return
    }
    setUploading({ done: 0, total: images.length })
    let done = 0
    let uploaded = 0
    for (const file of images) {
      const formData = new FormData()
      formData.append('image', file)
      try {
        await api.post<Photo>(photosPath(roomTypeId), undefined, { formData })
        uploaded += 1
      } catch (error) {
        toast.error(t('photos.uploadFailed', { name: file.name, reason: errorMessage(error, t) }))
      }
      done += 1
      setUploading({ done, total: images.length })
    }
    setUploading(null)
    setOrder(null)
    await invalidate()
    if (uploaded > 0) toast.success(t('photos.uploaded', { count: uploaded }))
  }

  if (photos.isError) return <ErrorState error={photos.error} onRetry={() => void photos.refetch()} />
  if (!photos.data) return <LoadingState variant="rows" rows={2} />

  const byId = new Map(photos.data.map((photo) => [photo.id, photo]))
  const list = (order ?? photos.data.map((photo) => photo.id)).map((id) => byId.get(id)).filter((photo): photo is Photo => Boolean(photo))

  function commit(ids: string[]) {
    setOrder(ids)
    reorder.mutate(ids)
  }

  function move(index: number, delta: number) {
    const ids = list.map((photo) => photo.id)
    commit(arrayMove(ids, index, index + delta))
  }

  function onDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const ids = list.map((photo) => photo.id)
    commit(arrayMove(ids, ids.indexOf(String(active.id)), ids.indexOf(String(over.id))))
  }

  function onDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    if (canEdit && event.dataTransfer.files.length) void upload(event.dataTransfer.files)
  }

  return (
    <div className="grid gap-4">
      {canEdit && (
        <label
          htmlFor={inputId}
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            'flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-border-strong bg-surface-2/50 px-6 py-8 text-center transition-colors',
            'hover:border-accent hover:bg-accent-soft/40 focus-within:ring-2 focus-within:ring-accent/55',
            dragging && 'border-accent bg-accent-soft/60',
          )}
        >
          <ImagePlus aria-hidden className="size-6 text-accent" />
          <span className="font-semibold text-fg">
            {uploading ? t('photos.uploading', { done: uploading.done, total: uploading.total }) : t('photos.drop')}
          </span>
          <span className="text-xs text-muted">{t('photos.dropHint')}</span>
          <input
            id={inputId}
            name="photos"
            type="file"
            accept={ACCEPT}
            multiple
            className="sr-only"
            disabled={Boolean(uploading)}
            onChange={(event) => {
              if (event.target.files?.length) void upload(event.target.files)
              event.target.value = ''
            }}
          />
        </label>
      )}

      {list.length === 0 ? (
        <p className="text-sm text-muted">{t('photos.empty')}</p>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={list.map((photo) => photo.id)} strategy={rectSortingStrategy}>
            <ul aria-label={label} className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
              {list.map((photo, index) => (
                <SortablePhoto
                  key={photo.id}
                  photo={photo}
                  index={index}
                  count={list.length}
                  canEdit={canEdit}
                  caption={tr(photo.caption, i18n.language)}
                  onMove={(delta) => move(index, delta)}
                  onEdit={() => setEditing(photo)}
                  onDelete={() => remove.mutateAsync(photo)}
                />
              ))}
            </ul>
          </SortableContext>
        </DndContext>
      )}

      {editing && (
        <CaptionDialog photo={editing} roomTypeId={roomTypeId} onClose={() => setEditing(null)} onSaved={() => void invalidate()} />
      )}
    </div>
  )
}

function SortablePhoto({
  photo,
  index,
  count,
  canEdit,
  caption,
  onMove,
  onEdit,
  onDelete,
}: {
  photo: Photo
  index: number
  count: number
  canEdit: boolean
  caption: string
  onMove: (delta: number) => void
  onEdit: () => void
  onDelete: () => Promise<unknown>
}) {
  const { t } = useTranslation('inventory')
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: photo.id, disabled: !canEdit })
  const number = index + 1
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn('group relative overflow-hidden rounded-lg border border-border bg-surface shadow-xs', isDragging && 'z-10 shadow-lg ring-2 ring-accent/40')}
    >
      <img src={photo.url} alt={caption || t('photos.photoN', { number })} loading="lazy" className="aspect-[3/2] w-full object-cover" />
      {index === 0 && (
        <span className="absolute top-2 left-2 rounded-full bg-surface/90 px-2 py-0.5 text-2xs font-bold text-fg shadow-xs">{t('photos.cover')}</span>
      )}
      <p className={cn('truncate px-2.5 pt-2 text-xs', caption ? 'text-fg' : 'text-subtle', !canEdit && 'pb-2.5')} title={caption || undefined}>
        {caption || t('photos.noCaption')}
      </p>
      {canEdit && (
        <div className="flex items-center gap-0.5 px-1.5 pt-0.5 pb-1.5">
          <button
            type="button"
            className="cursor-grab rounded p-1 text-subtle hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
            aria-label={t('photos.drag', { number })}
            {...attributes}
            {...listeners}
          >
            <GripVertical aria-hidden className="size-4" />
          </button>
          <span className="flex-1" />
          <Button variant="ghost" size="icon-sm" aria-label={t('photos.moveBefore', { number })} disabled={index === 0} onClick={() => onMove(-1)}>
            <ArrowLeft aria-hidden />
          </Button>
          <Button variant="ghost" size="icon-sm" aria-label={t('photos.moveAfter', { number })} disabled={index === count - 1} onClick={() => onMove(1)}>
            <ArrowRight aria-hidden />
          </Button>
          <Button variant="ghost" size="icon-sm" aria-label={t('photos.editCaption', { number })} onClick={onEdit}>
            <PencilLine aria-hidden />
          </Button>
          <ConfirmDialog
            title={t('photos.deleteTitle')}
            description={t('photos.deleteDescription')}
            confirmLabel={t('common:actions.delete')}
            onConfirm={onDelete}
            trigger={
              <Button variant="ghost" size="icon-sm" aria-label={t('photos.delete', { number })}>
                <Trash2 aria-hidden />
              </Button>
            }
          />
        </div>
      )}
    </li>
  )
}

function CaptionDialog({ photo, roomTypeId, onClose, onSaved }: {
  photo: Photo
  roomTypeId: string | null
  onClose: () => void
  onSaved: () => void
}) {
  const { t } = useTranslation('inventory')
  const [caption, setCaption] = useState<I18nText>(photo.caption ?? {})
  const save = useMutation({
    mutationFn: () => api.patch<Photo>(`${photosPath(roomTypeId)}${photo.id}/`, { caption }),
    onSuccess: () => {
      toast.success(t('photos.captionSaved'))
      onSaved()
      onClose()
    },
    onError: (error) => toast.error(errorMessage(error, t)),
  })
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            save.mutate()
          }}
        >
          <DialogHeader>
            <DialogTitle>{t('photos.captionTitle')}</DialogTitle>
          </DialogHeader>
          <img src={photo.url} alt="" className="aspect-[3/2] w-full rounded-lg object-cover" />
          <I18nTextInput label={t('photos.caption')} name="caption" value={caption} onChange={setCaption} />
          <DialogFooter>
            <Button variant="secondary" onClick={onClose}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" loading={save.isPending}>
              {t('common:actions.save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
