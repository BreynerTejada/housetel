import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { errorMessage } from '@/lib/errors'
import { Button } from './ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from './ui/dialog'
import { Input } from './ui/input'

export interface ConfirmDialogProps {
  /** Controlled mode; omit both and pass `trigger` for uncontrolled use. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
  trigger?: ReactNode
  title: ReactNode
  description?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /**
   * The action. The dialog shows a spinner while the promise is pending, closes when it resolves and,
   * when it rejects, stays open and shows the reason (backend `detail`).
   */
  onConfirm: () => unknown
  /** Extra fields (e.g. a reason textarea). */
  children?: ReactNode
  /** Extra validation from `children` (e.g. reason still empty). */
  confirmDisabled?: boolean
}

interface BaseProps extends ConfirmDialogProps {
  tone: 'default' | 'danger'
  confirmText?: string
}

function ConfirmDialogBase({
  open,
  onOpenChange,
  trigger,
  title,
  description,
  confirmLabel,
  cancelLabel,
  onConfirm,
  children,
  confirmDisabled = false,
  tone,
  confirmText,
}: BaseProps) {
  const { t } = useTranslation()
  const promptId = useId()
  const [innerOpen, setInnerOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [typed, setTyped] = useState('')

  const isOpen = open ?? innerOpen
  const textMatches = confirmText === undefined || typed.trim() === confirmText
  const canConfirm = textMatches && !confirmDisabled && !pending

  function setOpen(next: boolean) {
    if (!next) {
      setTyped('')
      setError(null)
    }
    if (open === undefined) setInnerOpen(next)
    onOpenChange?.(next)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!canConfirm) return
    setPending(true)
    setError(null)
    try {
      await onConfirm()
      setPending(false)
      setOpen(false)
    } catch (err) {
      setPending(false)
      setError(errorMessage(err, t))
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(next) => !pending && setOpen(next)}>
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogContent className="max-w-md" hideClose={pending}>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description && <DialogDescription>{description}</DialogDescription>}
          </DialogHeader>

          {children}

          {confirmText !== undefined && (
            <div className="grid gap-2 rounded-lg border border-danger/25 bg-danger-soft/50 p-3">
              <p id={promptId} className="text-sm text-muted">
                <Trans
                  i18nKey="confirm.typeToConfirm"
                  values={{ text: confirmText }}
                  components={{ strong: <strong className="num font-bold text-fg" /> }}
                />
              </p>
              <Input
                aria-label={t('confirm.inputLabel')}
                aria-describedby={promptId}
                autoComplete="off"
                spellCheck={false}
                value={typed}
                onChange={(event) => setTyped(event.target.value)}
                className="num bg-surface"
              />
            </div>
          )}

          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button variant="secondary" onClick={() => setOpen(false)} disabled={pending}>
              {cancelLabel ?? t('actions.cancel')}
            </Button>
            <Button type="submit" variant={tone === 'danger' ? 'danger' : 'primary'} disabled={!canConfirm} loading={pending}>
              {confirmLabel ?? t('actions.confirm')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Asks before running an action. */
export function ConfirmDialog(props: ConfirmDialogProps) {
  return <ConfirmDialogBase {...props} tone="default" />
}

/**
 * For risky money actions (refund, void, waive fee, cancel invoice — spec §3): the user must type
 * `confirmText` exactly (an amount or a reservation code) before the action is enabled.
 * The backend still requires `confirm: true` in the request body.
 */
export function DangerConfirmDialog({ confirmText, ...props }: ConfirmDialogProps & { confirmText: string }) {
  return <ConfirmDialogBase {...props} tone="danger" confirmText={confirmText} />
}
