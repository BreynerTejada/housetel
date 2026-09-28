import { ArrowRight, CircleAlert, Eye, EyeOff, RotateCcw, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { missingFromError, useConfigureImport, type FieldSpec, type JobDetail } from '../api'
import { groupFields, missingLabel, oneOfGroup } from '../lib/fields'

const NONE = '__none__'

/** Required fields (and "one of" groups) a mapping leaves out — same rule as the backend's `missing_required`. */
function missingOf(job: JobDetail, mapping: Record<string, string>): string[] {
  const missing = job.fields.filter((field) => field.required && !mapping[field.code]).map((field) => field.code)
  for (const group of job.one_of) if (!group.some((code) => mapping[code])) missing.push(group.join('|'))
  return missing
}

/**
 * Step 3a: which column of the file feeds each Housetel field. Titles in Spanish or English (and the preset's
 * own, e.g. Cloudbeds') come detected; the sample cells show what each column holds. A column feeds one field.
 */
export function MapColumnsView({ job, onNext }: { job: JobDetail; onNext: () => void }) {
  const { t } = useTranslation('imports')
  const [mapping, setMapping] = useState<Record<string, string>>(() => ({ ...job.mapping }))
  const [tried, setTried] = useState(false)
  // Fields shown from the start: the mapped ones and the required ones (the rest waits behind "show all"
  // so a Cloudbeds export does not open with 30 empty selects). Fixed at mount: unmapping keeps the row.
  const [shown] = useState(
    () =>
      new Set(
        job.fields
          .filter((field) => job.mapping[field.code] || field.required || oneOfGroup(field.code, job.one_of))
          .map((field) => field.code),
      ),
  )
  const [showAll, setShowAll] = useState(() => Object.keys(job.mapping).length === 0)
  const configure = useConfigureImport(job.id)
  const missing = useMemo(() => missingOf(job, mapping), [job, mapping])
  const serverMissing = missingFromError(configure.error)
  const shownMissing = tried ? (serverMissing.length ? serverMissing : missing) : []
  const missingFields = new Set(shownMissing.flatMap((code) => code.split('|')))
  const usedBy = useMemo(() => {
    const byHeader = new Map<string, string>()
    for (const [code, header] of Object.entries(mapping)) byHeader.set(header, code)
    return byHeader
  }, [mapping])
  const unused = job.headers.filter((header) => !usedBy.has(header))
  const detected = Object.keys(job.suggested_mapping).length
  const isVisible = (field: FieldSpec) => showAll || shown.has(field.code) || Boolean(mapping[field.code]) || missingFields.has(field.code)
  const hidden = job.fields.filter((field) => !isVisible(field)).length

  function assign(code: string, header: string) {
    setMapping((current) => {
      const next = { ...current }
      if (header === NONE) {
        delete next[code]
        return next
      }
      // a column feeds one field: it leaves the field that had it
      for (const [other, value] of Object.entries(next)) if (value === header && other !== code) delete next[other]
      next[code] = header
      return next
    })
  }

  function save() {
    setTried(true)
    if (missing.length) return
    configure.mutate({ mapping }, { onSuccess: onNext })
  }

  return (
    <div className="grid gap-5">
      <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface-2/50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="flex items-start gap-2 text-[13px] leading-5 text-muted">
          <Sparkles aria-hidden className="mt-0.5 size-4 shrink-0 text-accent" />
          {detected >= job.headers.length ? t('map.detectedAll', { count: detected }) : t('map.detected', { count: detected, total: job.headers.length })}
        </p>
        <div className="flex flex-wrap items-center gap-1 self-start sm:self-auto">
          {(hidden > 0 || showAll) && (
            <Button size="sm" variant="ghost" onClick={() => setShowAll(!showAll)} aria-pressed={showAll}>
              {showAll ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
              {showAll ? t('map.hideEmpty') : t('map.showAll', { count: hidden })}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => setMapping({ ...job.suggested_mapping })}>
            <RotateCcw aria-hidden />
            {t('map.restore')}
          </Button>
        </div>
      </div>

      {shownMissing.length > 0 && (
        <div role="alert" className="flex gap-2 rounded-lg bg-danger-soft px-4 py-3 text-[13px] text-danger-ink">
          <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>{t('map.missing', { fields: shownMissing.map((code) => missingLabel(t, code)).join(' · ') })}</span>
        </div>
      )}

      {groupFields(job.fields.filter(isVisible)).map(({ group, fields }) => (
        <section key={group} aria-labelledby={`map-group-${group}`} className="rounded-xl border border-border bg-surface shadow-xs">
          <h2 id={`map-group-${group}`} className="border-b border-border px-4 py-3 text-sm font-bold tracking-[-0.01em] sm:px-5">
            {t(`groups.${group}`)}
          </h2>
          <ul className="divide-y divide-border">
            {fields.map((field) => (
              <li key={field.code}>
                <FieldRow
                  field={field}
                  job={job}
                  header={mapping[field.code] ?? null}
                  usedBy={usedBy}
                  invalid={missingFields.has(field.code)}
                  onAssign={(header) => assign(field.code, header)}
                />
              </li>
            ))}
          </ul>
        </section>
      ))}

      {unused.length > 0 && (
        <section aria-labelledby="map-unused" className="grid gap-2 rounded-xl border border-dashed border-border-strong px-4 py-3 sm:px-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="map-unused" className="text-[13px] font-semibold text-muted">
              {t('map.unused', { count: unused.length })}
            </h2>
            {!showAll && hidden > 0 && (
              <Button size="sm" variant="link" onClick={() => setShowAll(true)}>
                {t('map.assignThem')}
              </Button>
            )}
          </div>
          <ul className="flex flex-wrap gap-1.5">
            {unused.map((header) => (
              <li key={header} className="max-w-full truncate rounded-sm border border-border bg-surface-2 px-1.5 py-0.5 text-xs text-muted">
                {header}
              </li>
            ))}
          </ul>
        </section>
      )}

      {configure.isError && !serverMissing.length && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {errorMessage(configure.error, t)}
        </p>
      )}

      <div className="sticky bottom-0 z-10 -mx-4 flex items-center justify-between gap-3 border-t border-border bg-bg/95 px-4 py-3 backdrop-blur sm:static sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none">
        <span className="num text-[13px] text-muted">{t('map.assigned', { count: Object.keys(mapping).length })}</span>
        <Button variant="primary" onClick={save} loading={configure.isPending}>
          {t('map.next')}
          <ArrowRight aria-hidden />
        </Button>
      </div>
    </div>
  )
}

function FieldRow({
  field,
  job,
  header,
  usedBy,
  invalid,
  onAssign,
}: {
  field: FieldSpec
  job: JobDetail
  header: string | null
  usedBy: Map<string, string>
  invalid: boolean
  onAssign: (header: string) => void
}) {
  const { t, i18n } = useTranslation('imports')
  const label = t(`fields.${field.code}`)
  const hintKey = `fieldHints.${field.code}`
  const group = oneOfGroup(field.code, job.one_of)
  const samples = header ? (job.samples[header] ?? []).slice(0, 3) : []
  const suggested = header !== null && job.suggested_mapping[field.code] === header
  const triggerId = `map-${field.code}`

  return (
    <div className="grid gap-2 px-4 py-3 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] sm:gap-5 sm:px-5">
      <div className="min-w-0">
        <label htmlFor={triggerId} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 font-semibold text-fg">
          {label}
          {field.required && <span className="text-xs font-semibold text-danger-ink">{t('map.required')}</span>}
          {!field.required && group && (
            <span className="text-xs font-medium text-muted">
              {t('map.oneOf', { fields: group.filter((code) => code !== field.code).map((code) => t(`fields.${code}`)).join(', ') })}
            </span>
          )}
        </label>
        {i18n.exists(hintKey, { ns: 'imports' }) && <p className="mt-0.5 text-xs leading-4 text-muted">{t(hintKey)}</p>}
      </div>
      <div className="grid min-w-0 gap-1.5">
        <Select value={header ?? NONE} onValueChange={onAssign}>
          <SelectTrigger id={triggerId} aria-invalid={invalid || undefined} className={cn(!header && 'text-subtle')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>{t('map.none')}</SelectItem>
            {job.headers.map((title) => {
              const owner = usedBy.get(title)
              return (
                <SelectItem key={title} value={title}>
                  {title}
                  {owner && owner !== field.code ? ` · ${t('map.usedBy', { field: t(`fields.${owner}`) })}` : ''}
                </SelectItem>
              )
            })}
          </SelectContent>
        </Select>
        <div className="flex min-h-5 flex-wrap items-center gap-1.5">
          {suggested && (
            <Badge tone="accent">
              <Sparkles aria-hidden />
              {t('map.auto')}
            </Badge>
          )}
          {header && samples.length === 0 && <span className="text-xs text-subtle">{t('map.emptyColumn')}</span>}
          {samples.map((sample) => (
            <span
              key={sample}
              title={sample}
              className="num max-w-[11rem] truncate rounded-sm border border-border bg-surface-2 px-1.5 py-0.5 text-xs text-muted"
            >
              {sample}
            </span>
          ))}
          {!header && <span className="text-xs text-subtle">{t('map.notImported')}</span>}
        </div>
      </div>
    </div>
  )
}
