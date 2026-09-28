import { Undo2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { DangerConfirmDialog } from '@/components/ConfirmDialog'
import { Button, type ButtonProps } from '@/components/ui/button'
import { useUndoAudit, type AuditEvent } from '../api'

/**
 * "Deshacer" for a reversible audited action: the user types the confirmation word, the backend receives
 * `{confirm: true}` and runs the action's undo handler. Errors (a newer change, already undone…) stay in the dialog.
 */
export function UndoButton({
  event,
  size = 'sm',
  variant = 'secondary',
  onUndone,
}: {
  event: Pick<AuditEvent, 'id' | 'summary' | 'action'>
  size?: ButtonProps['size']
  variant?: ButtonProps['variant']
  onUndone?: () => void
}) {
  const { t } = useTranslation('control')
  const undo = useUndoAudit()
  const word = t('audit.undoDialog.confirmWord')

  return (
    <DangerConfirmDialog
      trigger={
        <Button size={size} variant={variant}>
          <Undo2 aria-hidden />
          {t('audit.undo')}
        </Button>
      }
      title={t('audit.undoDialog.title')}
      description={t('audit.undoDialog.description', { summary: event.summary || event.action })}
      confirmText={word}
      confirmLabel={t('audit.undoDialog.confirm')}
      onConfirm={async () => {
        await undo.mutateAsync(event.id)
        toast.success(t('audit.toasts.undone'))
        onUndone?.()
      }}
    />
  )
}
