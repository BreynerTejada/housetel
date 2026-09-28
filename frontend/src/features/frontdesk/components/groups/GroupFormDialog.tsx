import { useQueryClient } from '@tanstack/react-query'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { isExistingGuest, useCreateGuest, type GuestPickerValue } from '@/features/guests/api'
import { GuestPicker } from '@/features/guests/components/GuestPicker'
import { errorMessage } from '@/lib/errors'
import { bookingKeys, createGroup, updateGroup, type GroupListItem } from '../../api'

/**
 * Create or edit a group (pilot P3): its name, who organizes it (an existing guest, or one created here) and
 * notes for the team.
 */
export function GroupFormDialog({
  open,
  onOpenChange,
  group,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Editing this group; creating a new one when absent. */
  group?: GroupListItem
  onSaved?: (group: GroupListItem) => void
}) {
  const { t } = useTranslation('frontdesk')
  const ids = { name: useId(), contact: useId(), notes: useId() }
  const queryClient = useQueryClient()
  const createGuest = useCreateGuest()
  const [name, setName] = useState(group?.name ?? '')
  const [notes, setNotes] = useState(group?.notes ?? '')
  const [contact, setContact] = useState<GuestPickerValue | null>(null)
  const [keepContact, setKeepContact] = useState(Boolean(group?.contact_guest))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save() {
    setSaving(true)
    setError(null)
    try {
      let contactId: string | null = keepContact && group?.contact_guest ? group.contact_guest.id : null
      if (contact) contactId = isExistingGuest(contact) ? contact.id : (await createGuest.mutateAsync(contact)).id
      const input = { name: name.trim(), notes: notes.trim(), contact_guest_id: contactId }
      const saved = group ? await updateGroup(group.id, input) : await createGroup(input)
      await queryClient.invalidateQueries({ queryKey: ['bookings', 'groups'] })
      if (group) await queryClient.invalidateQueries({ queryKey: bookingKeys.group(group.id) })
      toast.success(group ? t('groups.form.saved') : t('groups.form.created', { name: saved.name }))
      onSaved?.(saved)
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err, t))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{group ? t('groups.form.editTitle') : t('groups.form.title')}</DialogTitle>
          <DialogDescription>{t('groups.form.description')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor={ids.name} className="font-semibold">
              {t('groups.form.name')}
            </Label>
            <Input id={ids.name} value={name} onChange={(event) => setName(event.target.value)} placeholder={t('wizard.group.namePlaceholder')} maxLength={200} autoFocus />
          </div>
          <div className="grid gap-2">
            <Label htmlFor={ids.contact} className="font-semibold">
              {t('groups.form.contact')}
            </Label>
            {keepContact && group?.contact_guest && !contact ? (
              <div className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 text-[13px]">
                <span className="min-w-0 truncate font-semibold text-fg">{group.contact_guest.full_name}</span>
                <Button size="sm" variant="ghost" onClick={() => setKeepContact(false)}>
                  {t('groups.form.changeContact')}
                </Button>
              </div>
            ) : (
              <GuestPicker id={ids.contact} value={contact} onChange={setContact} />
            )}
            <p className="text-xs text-muted">{t('groups.form.contactHint')}</p>
          </div>
          <div className="grid gap-2">
            <Label htmlFor={ids.notes} className="font-semibold">
              {t('groups.form.notes')}
            </Label>
            <Textarea id={ids.notes} value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} placeholder={t('groups.form.notesPlaceholder')} />
          </div>
          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={saving}>
            {t('common:actions.cancel')}
          </Button>
          <Button variant="primary" onClick={() => void save()} loading={saving} disabled={!name.trim()}>
            {group ? t('common:actions.saveChanges') : t('groups.form.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
