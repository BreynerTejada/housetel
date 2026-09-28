import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { CircleAlert, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '@/components/ErrorState'
import { Badge } from '@/components/ui/badge'
import { useActiveProperty } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { previewTemplate, type Language, type SendChannel } from '../../api'
import { useDebounced } from '../../lib/useDebounced'
import { WhatsAppText } from '../WhatsAppText'

/**
 * The draft as the guest receives it, with believable sample data: the real email (Housetel layout with the
 * hotel's name and color) or the WhatsApp bubble. Flags variables that would come out empty.
 */
export function TemplatePreview({
  code,
  channel,
  language,
  subject,
  body,
}: {
  code: string
  channel: SendChannel
  language: Language
  subject: string
  body: string
}) {
  const { t } = useTranslation('messaging')
  const { property } = useActiveProperty()
  const draft = useDebounced({ code, channel, language, subject: channel === 'email' ? subject : '', body }, 400)
  const preview = useQuery({
    queryKey: ['messaging', 'template-preview', draft],
    queryFn: () =>
      previewTemplate({
        channel: draft.channel,
        language: draft.language,
        template_code: draft.code,
        subject: draft.subject,
        body: draft.body,
      }),
    placeholderData: keepPreviousData,
  })
  const data = preview.data

  return (
    <section aria-labelledby="template-preview-title" className="grid content-start gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="template-preview-title" className="eyebrow">
          {t('settings.templates.preview')}
        </h3>
        <Badge tone="neutral">{t('settings.templates.previewSample')}</Badge>
      </div>
      {preview.isError && !data ? (
        <ErrorState error={preview.error} onRetry={() => preview.refetch()} />
      ) : channel === 'email' ? (
        <div className={cn('overflow-hidden rounded-xl border border-border bg-surface shadow-xs transition-opacity', preview.isFetching && 'opacity-75')}>
          <div className="grid gap-0.5 border-b border-border px-4 py-3 text-[13px]">
            <p className="truncate text-muted">
              {t('settings.templates.from')} <span className="font-semibold text-fg">{property?.name}</span>
            </p>
            <p className="font-bold break-words">{data?.subject || <span className="font-normal text-subtle">{t('settings.templates.noSubject')}</span>}</p>
          </div>
          {data ? (
            <iframe
              title={t('settings.templates.previewEmail')}
              srcDoc={data.html}
              sandbox=""
              className="block h-[34rem] w-full bg-[#FAF8F5]"
            />
          ) : (
            <div className="h-[34rem] animate-pulse bg-surface-2" />
          )}
        </div>
      ) : (
        <div className={cn('hatch rounded-xl border border-border p-4 transition-opacity', preview.isFetching && 'opacity-75')}>
          <p className="w-fit max-w-[92%] rounded-xl rounded-tl-sm bg-surface px-3 pt-2 pb-1.5 text-[14px] leading-snug break-words whitespace-pre-wrap text-fg shadow-xs">
            {data ? <WhatsAppText text={data.whatsapp || ' '} /> : ' '}
            <span className="float-right mt-1.5 ml-3 text-[10px] text-muted">09:05</span>
          </p>
        </div>
      )}
      {data && data.unknown.length > 0 && (
        <p className="flex items-start gap-1.5 text-[12.5px] text-danger-ink">
          <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          {t('settings.templates.unknown', { names: data.unknown.join(', ') })}
        </p>
      )}
      {data && data.missing.length > 0 && (
        <p className="flex items-start gap-1.5 text-[12.5px] text-warning-ink">
          <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          {t('settings.templates.missing', { names: data.missing.join(', ') })}
        </p>
      )}
    </section>
  )
}
