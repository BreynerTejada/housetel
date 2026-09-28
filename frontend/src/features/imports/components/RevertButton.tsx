import { Undo2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DangerConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { formatNumber, normalizeLang } from '@/lib/format'
import { useRevertPreview, useStartImport, type JobDetail } from '../api'

/**
 * Rolls back a reservations import: cancels (no fee) the reservations the job created that nobody touched
 * since — no other payments, charges or changes by people — after voiding their imported payment. In-house
 * reservations and the ones with activity stay. Typed confirmation, as every risky bulk action.
 */
export function RevertButton({ job }: { job: JobDetail }) {
  const { t, i18n } = useTranslation('imports')
  const lang = normalizeLang(i18n.language)
  const [open, setOpen] = useState(false)
  const preview = useRevertPreview(job.id, open)
  const start = useStartImport(job.id)
  const data = preview.data
  const kept = data ? data.in_house + data.activity + data.not_active + data.missing : 0

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Undo2 aria-hidden />
        {t('revert.button')}
      </Button>
      <DangerConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={t('revert.title')}
        description={t('revert.description')}
        confirmText={t('revert.word')}
        confirmLabel={t('revert.confirm')}
        confirmDisabled={!data || data.revertible === 0}
        onConfirm={() => start.mutateAsync({ mode: 'revert', confirm: true })}
      >
        {preview.isPending ? (
          <p className="text-sm text-muted">{t('revert.loading')}</p>
        ) : data ? (
          <div className="grid gap-2 rounded-lg border border-border bg-surface-2/60 p-3 text-sm">
            <p className="font-semibold text-fg">
              {t('revert.revertible', { count: data.revertible, formatted: formatNumber(data.revertible, lang, 0) })}
            </p>
            {kept > 0 && (
              <ul className="grid gap-0.5 text-[13px] text-muted">
                {data.in_house > 0 && <li>{t('revert.inHouse', { count: data.in_house })}</li>}
                {data.activity > 0 && <li>{t('revert.activity', { count: data.activity })}</li>}
                {data.not_active > 0 && <li>{t('revert.notActive', { count: data.not_active })}</li>}
                {data.missing > 0 && <li>{t('revert.missing', { count: data.missing })}</li>}
              </ul>
            )}
          </div>
        ) : null}
      </DangerConfirmDialog>
    </>
  )
}
