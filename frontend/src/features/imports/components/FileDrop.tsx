import { FileUp, LoaderCircle } from 'lucide-react'
import { useId, useRef, useState, type DragEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { ACCEPTED_EXTENSIONS } from '../api'

const ACCEPT = [...ACCEPTED_EXTENSIONS, 'text/csv', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'].join(',')

/** Step 2: drop the CSV / Excel file here (or pick it). The parent validates and uploads it. */
export function FileDrop({
  onFile,
  busyName,
  error,
  disabled = false,
}: {
  onFile: (file: File) => void
  /** Name of the file being uploaded (shows the spinner). */
  busyName?: string | null
  error?: string | null
  disabled?: boolean
}) {
  const { t } = useTranslation('imports')
  const inputId = useId()
  const hintId = useId()
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const busy = Boolean(busyName)

  function take(files: FileList | null) {
    const file = files?.[0]
    if (file) onFile(file)
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setOver(false)
    if (disabled || busy) return
    take(event.dataTransfer.files)
  }

  return (
    <div className="grid gap-2">
      <div
        onDragEnter={(event) => {
          event.preventDefault()
          if (!disabled && !busy) setOver(true)
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(false)
        }}
        onDrop={drop}
        className={cn(
          'flex flex-col items-center gap-3 rounded-xl border-2 border-dashed px-5 py-8 text-center transition-colors',
          over ? 'border-accent bg-accent-soft/50' : 'border-border-strong bg-surface-2/40',
          error && !over && 'border-danger/60',
          (disabled || busy) && 'opacity-80',
        )}
      >
        <span
          aria-hidden
          className={cn(
            'grid size-11 place-items-center rounded-xl border bg-surface shadow-xs',
            over ? 'border-accent/40 text-accent-ink' : 'border-border text-muted',
          )}
        >
          {busy ? <LoaderCircle className="size-5 animate-spin text-accent" /> : <FileUp className="size-5" />}
        </span>
        {busy ? (
          <p role="status" className="text-sm font-semibold text-fg">
            {t('upload.uploading', { name: busyName })}
          </p>
        ) : (
          <div className="grid gap-1">
            <p className="text-[15px] font-semibold text-fg">{over ? t('upload.release') : t('upload.drop')}</p>
            <p id={hintId} className="text-[13px] text-muted">
              {t('upload.limits')}
            </p>
          </div>
        )}
        <input
          ref={input}
          id={inputId}
          type="file"
          accept={ACCEPT}
          className="sr-only"
          tabIndex={-1}
          disabled={disabled || busy}
          onChange={(event) => {
            take(event.target.files)
            event.target.value = ''
          }}
        />
        <Button variant="primary" onClick={() => input.current?.click()} disabled={disabled || busy} aria-describedby={hintId}>
          <FileUp aria-hidden />
          {t('upload.choose')}
        </Button>
      </div>
      {error && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {error}
        </p>
      )}
    </div>
  )
}
