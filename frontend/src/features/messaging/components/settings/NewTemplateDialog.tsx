import { Mail, MessageCircle } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { isApiError } from '@/lib/api'
import { useActiveMembership } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { createTemplate, useMessagingMutation, type Language, type SendChannel } from '../../api'
import { slugifyCode } from '../../lib/templates'
import { Segmented } from '../Segmented'

const CODE_RE = /^[a-z][a-z0-9_]{1,63}$/

/** A template of the hotel's own (e.g. a welcome drink offer) to send by hand or from an automatic message. */
export function NewTemplateDialog({
  open,
  onOpenChange,
  existingCodes,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  existingCodes: string[]
  onCreated: (code: string) => void
}) {
  const { t } = useTranslation('messaging')
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('settings.templates.newTitle')}</DialogTitle>
          <DialogDescription>{t('settings.templates.newDescription')}</DialogDescription>
        </DialogHeader>
        {open && (
          <NewTemplateForm
            existingCodes={existingCodes}
            onCreated={(code) => {
              onOpenChange(false)
              onCreated(code)
            }}
            onCancel={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function NewTemplateForm({ existingCodes, onCreated, onCancel }: { existingCodes: string[]; onCreated: (code: string) => void; onCancel: () => void }) {
  const { t, i18n } = useTranslation('messaging')
  const ids = useId()
  const membership = useActiveMembership()
  const chain = (membership?.properties.length ?? 0) > 1
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [codeEdited, setCodeEdited] = useState(false)
  const [channel, setChannel] = useState<SendChannel>('whatsapp')
  const [language, setLanguage] = useState<Language>(normalizeLang(i18n.language))
  const [scope, setScope] = useState<'property' | 'organization'>('property')
  const [tried, setTried] = useState(false)
  const effectiveCode = codeEdited ? code : slugifyCode(name)
  const nameError = tried && !name.trim() ? t('settings.templates.nameRequired') : ''
  const codeError = !tried
    ? ''
    : !CODE_RE.test(effectiveCode)
      ? t('settings.templates.codeHint')
      : existingCodes.includes(effectiveCode)
        ? t('settings.templates.codeTaken')
        : ''

  const create = useMessagingMutation(
    () =>
      createTemplate({
        code: effectiveCode,
        name: name.trim(),
        channel,
        language,
        scope,
        subject: channel === 'email' ? name.trim() : '',
        body: `${t('settings.templates.starter', { variable: '{{guest.first_name}}' })}\n\n`,
      }),
    {
      onSuccess: (row) => {
        toast.success(t('settings.templates.created'))
        onCreated(row.code)
      },
    },
  )

  function submit(event: FormEvent) {
    event.preventDefault()
    setTried(true)
    if (!name.trim() || !CODE_RE.test(effectiveCode) || existingCodes.includes(effectiveCode)) return
    create.mutate(undefined)
  }

  const serverFields = isApiError(create.error) ? (create.error.fields ?? {}) : {}

  return (
    <form onSubmit={submit} noValidate className="grid gap-4">
      <div className="grid gap-1.5">
        <Label htmlFor={`${ids}-name`}>{t('settings.templates.name')}</Label>
        <Input
          id={`${ids}-name`}
          name="name"
          value={name}
          maxLength={120}
          onChange={(event) => setName(event.target.value)}
          placeholder={t('settings.templates.namePlaceholder')}
          aria-invalid={Boolean(nameError) || undefined}
        />
        {nameError && <p className="text-[12.5px] text-danger-ink">{nameError}</p>}
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${ids}-code`}>{t('settings.templates.code')}</Label>
        <Input
          id={`${ids}-code`}
          name="code"
          value={effectiveCode}
          maxLength={64}
          onChange={(event) => {
            setCodeEdited(true)
            setCode(event.target.value.toLowerCase())
          }}
          className="num"
          aria-describedby={`${ids}-code-hint`}
          aria-invalid={Boolean(codeError || serverFields.code) || undefined}
        />
        <p id={`${ids}-code-hint`} className={codeError || serverFields.code ? 'text-[12.5px] text-danger-ink' : 'text-[12.5px] text-muted'}>
          {codeError || serverFields.code?.join(' ') || t('settings.templates.codeHint')}
        </p>
      </div>
      <div className="flex flex-wrap gap-4">
        <div className="grid gap-1.5">
          <p className="text-[13px] font-semibold">{t('settings.templates.channel')}</p>
          <Segmented
            label={t('settings.templates.channel')}
            value={channel}
            onChange={setChannel}
            options={[
              { value: 'whatsapp', label: t('channels.whatsapp'), icon: MessageCircle },
              { value: 'email', label: t('channels.email'), icon: Mail },
            ]}
          />
        </div>
        <div className="grid gap-1.5">
          <p className="text-[13px] font-semibold">{t('settings.templates.language')}</p>
          <Segmented
            label={t('settings.templates.language')}
            value={language}
            onChange={setLanguage}
            options={[
              { value: 'es', label: t('languages.es') },
              { value: 'en', label: t('languages.en') },
            ]}
          />
        </div>
      </div>
      {chain && (
        <div className="grid gap-1.5">
          <p className="text-[13px] font-semibold">{t('settings.templates.scope')}</p>
          <Segmented
            label={t('settings.templates.scope')}
            value={scope}
            onChange={setScope}
            options={[
              { value: 'property', label: t('settings.templates.scopes.property') },
              { value: 'organization', label: t('settings.templates.scopes.organization') },
            ]}
          />
        </div>
      )}
      {create.error && !serverFields.code && (
        <p role="alert" className="text-[13px] text-danger-ink">
          {errorMessage(create.error, t)}
        </p>
      )}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t('common:actions.cancel')}
        </Button>
        <Button type="submit" variant="primary" loading={create.isPending}>
          {t('settings.templates.create')}
        </Button>
      </DialogFooter>
    </form>
  )
}
