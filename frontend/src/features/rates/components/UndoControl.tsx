import { Undo2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import type { UndoStack } from '../hooks/useUndoStack'

export function UndoButton({ state }: { state: UndoStack }) {
  const { t } = useTranslation('rates')
  const hint = !state.allowed ? t('undo.forbidden') : state.lastId ? t('undo.hint') : t('undo.empty')
  return (
    <Button onClick={state.undo} disabled={!state.canUndo} loading={state.pending} title={hint}>
      <Undo2 aria-hidden />
      {t('undo.action')}
    </Button>
  )
}
