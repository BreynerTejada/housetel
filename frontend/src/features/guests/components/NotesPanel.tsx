import { Plus, X } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { useGuestTags, useUpdateGuest, type Guest } from '../api'

interface PreferenceRow {
  id: number
  key: string
  value: string
}

function rowsOf(preferences: Record<string, string>): PreferenceRow[] {
  return Object.entries(preferences ?? {}).map(([key, value], index) => ({ id: index, key, value: String(value) }))
}

/** Internal notes, stay preferences and tags of the guest. */
export function NotesPanel({ guest, readOnly }: { guest: Guest; readOnly: boolean }) {
  const { t } = useTranslation('guests')
  const baseId = useId()
  const canManage = useCan('guests.manage') && !readOnly
  const update = useUpdateGuest(guest.id)
  const knownTags = useGuestTags()
  const [notes, setNotes] = useState(guest.notes)
  const [rows, setRows] = useState<PreferenceRow[]>(() => rowsOf(guest.preferences))
  const [tags, setTags] = useState<string[]>(guest.tags)
  const [tagDraft, setTagDraft] = useState('')

  function addTag() {
    const tag = tagDraft.trim()
    if (tag && !tags.includes(tag)) setTags([...tags, tag])
    setTagDraft('')
  }

  async function save() {
    const preferences = Object.fromEntries(
      rows.filter((row) => row.key.trim()).map((row) => [row.key.trim(), row.value.trim()]),
    )
    try {
      await update.mutateAsync({ notes, preferences, tags })
      toast.success(t('notes.saved'))
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card className="lg:row-span-2">
        <CardHeader>
          <CardTitle>
            <label htmlFor={`${baseId}-notes`}>{t('notes.notes')}</label>
          </CardTitle>
          <CardDescription>{t('notes.notesHint')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Textarea
            id={`${baseId}-notes`}
            name="notes"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            readOnly={!canManage}
            rows={10}
            className="min-h-48"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('notes.preferences')}</CardTitle>
          <CardDescription>{t('notes.preferencesHint')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2">
          {rows.map((row, index) => (
            <div key={row.id} className="grid grid-cols-[1fr_1.4fr_auto] items-center gap-2">
              <Input
                aria-label={t('notes.key')}
                name={`preference-key-${index}`}
                value={row.key}
                readOnly={!canManage}
                placeholder={t('notes.key')}
                onChange={(event) => setRows(rows.map((r) => (r.id === row.id ? { ...r, key: event.target.value } : r)))}
              />
              <Input
                aria-label={t('notes.value')}
                name={`preference-value-${index}`}
                value={row.value}
                readOnly={!canManage}
                placeholder={t('notes.value')}
                onChange={(event) => setRows(rows.map((r) => (r.id === row.id ? { ...r, value: event.target.value } : r)))}
              />
              {canManage && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t('notes.removePreference', { key: row.key })}
                  onClick={() => setRows(rows.filter((r) => r.id !== row.id))}
                >
                  <X aria-hidden />
                </Button>
              )}
            </div>
          ))}
          {canManage && (
            <Button
              variant="ghost"
              size="sm"
              className="justify-self-start"
              onClick={() => setRows([...rows, { id: Date.now(), key: '', value: '' }])}
            >
              <Plus aria-hidden />
              {t('notes.addPreference')}
            </Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('notes.tags')}</CardTitle>
          <CardDescription>{t('notes.tagsHint')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {tags.length > 0 ? (
            <ul className="flex flex-wrap gap-1.5">
              {tags.map((tag) => (
                <li key={tag} className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-2 py-0.5 pr-1 pl-2.5 text-xs font-semibold text-fg">
                  {tag}
                  {canManage && (
                    <button
                      type="button"
                      aria-label={t('notes.removeTag', { tag })}
                      onClick={() => setTags(tags.filter((item) => item !== tag))}
                      className="grid size-5 place-items-center rounded-full text-muted hover:bg-surface-3 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                    >
                      <X aria-hidden className="size-3" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">{t('detail.noTags')}</p>
          )}
          {canManage && (
            <div className="grid gap-1.5">
              <Label htmlFor={`${baseId}-tag`}>{t('notes.tagInput')}</Label>
              <Input
                id={`${baseId}-tag`}
                name="tag"
                list={`${baseId}-tags`}
                value={tagDraft}
                placeholder={t('notes.tagPlaceholder')}
                onChange={(event) => setTagDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ',') {
                    event.preventDefault()
                    addTag()
                  }
                }}
                onBlur={addTag}
              />
              <datalist id={`${baseId}-tags`}>
                {(knownTags.data ?? []).filter((tag) => !tags.includes(tag)).map((tag) => (
                  <option key={tag} value={tag} />
                ))}
              </datalist>
            </div>
          )}
        </CardContent>
      </Card>

      {canManage && (
        <div className="lg:col-span-2 lg:flex lg:justify-end">
          <Button variant="primary" onClick={save} loading={update.isPending}>
            {t('notes.save')}
          </Button>
        </div>
      )}
    </div>
  )
}
