import { Info, Lock } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { PageHeader } from '@/components/PageHeader'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { errorMessage } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { MAX_FILE_BYTES, useUploadImport, type ImportKind, type ImportPreset } from '../api'
import { FileDrop } from '../components/FileDrop'
import { ImportStepper } from '../components/ImportStepper'
import { JobHistory } from '../components/JobHistory'
import { KindPicker, PresetPicker } from '../components/KindPicker'
import { TemplatesMenu } from '../components/TemplatesMenu'

const READABLE = /\.(csv|xlsx|xlsm|txt)$/i

/**
 * `/app/settings/import`: steps 1 and 2 of the importer — what the file brings and where it comes from, then
 * the upload (templates and an example file at hand) — and the history of imports of the property.
 */
export default function ImportPage() {
  const { t } = useTranslation('imports')
  const canImport = useCan('imports.run')
  const navigate = useNavigate()
  const sourceId = useId()
  const [kind, setKind] = useState<ImportKind>('reservations')
  const [preset, setPreset] = useState<ImportPreset>('cloudbeds')
  const [sourceLabel, setSourceLabel] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const [uploading, setUploading] = useState<string | null>(null)
  const upload = useUploadImport()

  if (!canImport) {
    return (
      <div className="grid gap-5">
        <PageHeader title={t('page.title')} description={t('page.description')} className="pb-0" />
        <EmptyState icon={Lock} title={t('page.forbidden')} description={t('page.forbiddenHint')} />
      </div>
    )
  }

  function pick(file: File) {
    setLocalError(null)
    upload.reset()
    if (/\.xls$/i.test(file.name)) return setLocalError(t('upload.errors.xls'))
    if (!READABLE.test(file.name)) return setLocalError(t('upload.errors.type'))
    if (file.size > MAX_FILE_BYTES) return setLocalError(t('upload.errors.size'))
    if (file.size === 0) return setLocalError(t('upload.errors.empty'))
    setUploading(file.name)
    upload.mutate(
      { kind, preset, file, source_label: preset === 'generic' ? sourceLabel : '' },
      {
        onSuccess: (job) => navigate(`/app/settings/import/${job.id}`),
        onSettled: () => setUploading(null),
      },
    )
  }

  const error = localError ?? (upload.isError ? errorMessage(upload.error, t) : null)

  return (
    <div className="grid gap-6">
      <PageHeader title={t('page.title')} description={t('page.description')} className="pb-0" />
      <ImportStepper current="kind" />

      <section aria-labelledby="imports-new" className="grid gap-6 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5">
        <h2 id="imports-new" className="sr-only">
          {t('start.title')}
        </h2>

        <div className="grid gap-3">
          <p className="eyebrow">{t('start.kindStep')}</p>
          <KindPicker value={kind} onChange={setKind} />
          <p className="flex gap-2 text-[13px] leading-5 text-muted">
            <Info aria-hidden className="mt-0.5 size-3.5 shrink-0 text-subtle" />
            {t('start.order')}
          </p>
        </div>

        <div className="grid gap-3">
          <p className="eyebrow">{t('start.presetStep')}</p>
          <PresetPicker value={preset} onChange={setPreset} />
          {preset === 'cloudbeds' ? (
            <p className="rounded-lg bg-surface-2/70 px-3 py-2.5 text-[13px] leading-5 text-muted">{t(`howto.cloudbeds.${kind}`)}</p>
          ) : (
            <div className="grid gap-1.5 sm:max-w-sm">
              <Label htmlFor={sourceId}>{t('start.sourceLabel')}</Label>
              <Input
                id={sourceId}
                value={sourceLabel}
                maxLength={100}
                placeholder={t('start.sourcePlaceholder')}
                onChange={(event) => setSourceLabel(event.target.value)}
              />
              <p className="text-xs text-muted">{t('start.sourceHint')}</p>
            </div>
          )}
        </div>

        <div className="grid gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="eyebrow">{t('start.fileStep')}</p>
            <TemplatesMenu kind={kind} preset={preset} />
          </div>
          <FileDrop onFile={pick} busyName={uploading} error={error} />
          <p className="text-xs leading-5 text-muted">{t('start.privacy')}</p>
        </div>
      </section>

      <JobHistory />
    </div>
  )
}
