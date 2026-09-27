import { Download, Eye, FileText, Lock, Trash2, Upload } from 'lucide-react'
import { useState, type DragEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  DOCUMENT_KINDS,
  saveBlob,
  useDeleteDocument,
  useGuestDocuments,
  useUploadDocument,
  type DocumentKind,
  type GuestDocument,
} from '../api'
import { usePrivateFileUrl } from '../hooks'

const ACCEPT = 'image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf'

/** Identity documents of the guest. Files are private: previews are fetched with the session. */
export function DocumentsPanel({ guestId, readOnly }: { guestId: string; readOnly: boolean }) {
  const { t } = useTranslation('guests')
  const canManage = useCan('guests.manage') && !readOnly
  const documents = useGuestDocuments(guestId)
  const upload = useUploadDocument(guestId)
  const [kind, setKind] = useState<DocumentKind>('id_front')
  const [dragging, setDragging] = useState(false)

  async function send(file: File | undefined) {
    if (!file) return
    try {
      await upload.mutateAsync({ kind, file })
      toast.success(t('documents.uploaded'))
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    void send(event.dataTransfer.files[0])
  }

  return (
    <div className="grid gap-5">
      {canManage && (
        <div
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            'grid gap-4 rounded-xl border border-dashed border-border-strong bg-surface p-5 transition-colors sm:grid-cols-[1fr_auto] sm:items-center',
            dragging && 'border-accent bg-accent-soft/40',
          )}
        >
          <div className="flex items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-surface-2 text-muted">
              <Upload aria-hidden className="size-5" />
            </span>
            <div>
              <p className="font-semibold text-fg">{t('documents.dropzone')}</p>
              <p className="text-xs text-muted">{t('documents.dropzoneHint')}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1.5">
              <Label htmlFor={`kind-${guestId}`} className="text-xs">
                {t('documents.kind')}
              </Label>
              <Select name="document_kind" value={kind} onValueChange={(value) => setKind(value as DocumentKind)}>
                <SelectTrigger id={`kind-${guestId}`} className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DOCUMENT_KINDS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {t(`documents.kinds.${item}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <label
              className={cn(
                'inline-flex h-9 cursor-pointer items-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-on-accent shadow-xs hover:bg-accent-hover',
                'focus-within:ring-2 focus-within:ring-accent/55 focus-within:ring-offset-2 focus-within:ring-offset-bg',
                upload.isPending && 'pointer-events-none opacity-60',
              )}
            >
              <Upload aria-hidden className="size-4" />
              {t('documents.choose')}
              <input
                type="file"
                accept={ACCEPT}
                aria-label={t('documents.choose')}
                className="sr-only"
                disabled={upload.isPending}
                onChange={(event) => {
                  void send(event.target.files?.[0])
                  event.target.value = ''
                }}
              />
            </label>
          </div>
        </div>
      )}

      {documents.isPending ? (
        <LoadingState variant="rows" rows={2} />
      ) : documents.isError ? (
        <ErrorState error={documents.error} onRetry={() => void documents.refetch()} />
      ) : documents.data.length === 0 ? (
        <EmptyState icon={FileText} title={t('documents.empty')} />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {documents.data.map((document) => (
            <DocumentCard key={document.id} document={document} canManage={canManage} />
          ))}
        </ul>
      )}
    </div>
  )
}

function formatSize(bytes: number | null): string {
  if (!bytes) return ''
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function DocumentCard({ document, canManage }: { document: GuestDocument; canManage: boolean }) {
  const { t, i18n } = useTranslation('guests')
  const lang = normalizeLang(i18n.language)
  const file = usePrivateFileUrl(document.file_url)
  const remove = useDeleteDocument()
  const [confirming, setConfirming] = useState(false)
  const label = t(`documents.kinds.${document.kind}`)
  const isImage = document.content_type.startsWith('image/') && document.content_type !== 'image/heic'

  return (
    <li className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs">
      <div className="relative grid aspect-[4/3] place-items-center overflow-hidden bg-surface-2">
        {file.isLoading ? (
          <Skeleton className="size-full rounded-none" />
        ) : file.isError ? (
          <p className="px-4 text-center text-xs text-muted">{t('documents.loadError')}</p>
        ) : isImage && file.url ? (
          <img src={file.url} alt={label} className="size-full object-contain" />
        ) : (
          <FileText aria-hidden className="size-10 text-subtle" />
        )}
        <Badge tone="outline" className="absolute top-2 left-2 bg-surface/90">
          <Lock aria-hidden />
          {t('documents.private')}
        </Badge>
      </div>
      <div className="grid gap-2 p-3">
        <div>
          <p className="font-semibold text-fg">{label}</p>
          <p className="text-xs text-muted">
            {[t(`documents.via.${document.uploaded_via}`), formatDate(document.created_at, undefined, lang), formatSize(document.size)]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Button size="sm" variant="secondary" disabled={!file.url} onClick={() => file.url && window.open(file.url, '_blank', 'noopener')}>
            <Eye aria-hidden />
            {t('documents.view')}
          </Button>
          <Button size="sm" variant="ghost" disabled={!file.blob} onClick={() => file.blob && saveBlob(file.blob, document.filename)}>
            <Download aria-hidden />
            {t('documents.download')}
          </Button>
          {canManage && (
            <Button size="sm" variant="ghost" className="ml-auto text-danger-ink hover:bg-danger-soft" onClick={() => setConfirming(true)}>
              <Trash2 aria-hidden />
              {t('documents.delete')}
            </Button>
          )}
        </div>
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t('documents.deleteTitle')}
        description={t('documents.deleteDescription')}
        confirmLabel={t('documents.delete')}
        onConfirm={async () => {
          await remove.mutateAsync(document.id)
          toast.success(t('documents.deleted'))
        }}
      />
    </li>
  )
}
