import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api } from '@/lib/api'
import { ME_QUERY_KEY, useMe, type Me } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import i18n, { LANGUAGES } from '@/lib/i18n'

const schema = z.object({
  full_name: z.string().trim().min(1, 'validation.required'),
  phone: z.string().trim(),
  language: z.enum(LANGUAGES),
})
type ProfileValues = z.infer<typeof schema>

/** Edits the fields `PATCH /accounts/me/` accepts: full_name, phone, language. */
export function ProfileDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation()
  const { data: me } = useMe()
  const queryClient = useQueryClient()
  const form = useForm<ProfileValues>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: '', phone: '', language: 'es' },
  })

  useEffect(() => {
    if (open && me) form.reset({ full_name: me.full_name, phone: me.phone ?? '', language: me.language })
  }, [open, me, form])

  const save = useMutation({
    mutationFn: (values: ProfileValues) => api.patch<Me>('/accounts/me/', values),
    onSuccess: async (updated) => {
      queryClient.setQueryData(ME_QUERY_KEY, updated)
      if (updated.language && updated.language !== i18n.language) await i18n.changeLanguage(updated.language)
      toast.success(t('profile.saved'))
      onOpenChange(false)
    },
    onError: (error) => toast.error(errorMessage(error, t)),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={form.handleSubmit((values) => save.mutate(values))} className="grid gap-5" noValidate>
          <DialogHeader>
            <DialogTitle>{t('profile.title')}</DialogTitle>
            <DialogDescription>{t('profile.description')}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-1.5">
              <span className="text-[13px] font-semibold text-fg">{t('profile.email')}</span>
              <span className="text-sm text-muted">{me?.email}</span>
            </div>
            <FormField
              control={form.control}
              name="full_name"
              label={t('profile.fullName')}
              render={({ field, ...a11y }) => <Input autoComplete="name" {...field} {...a11y} />}
            />
            <FormField
              control={form.control}
              name="phone"
              label={t('profile.phone')}
              render={({ field, ...a11y }) => <Input type="tel" autoComplete="tel" {...field} {...a11y} />}
            />
            <FormField
              control={form.control}
              name="language"
              label={t('profile.language')}
              render={({ field, id, ...a11y }) => (
                <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id={id} {...a11y}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {LANGUAGES.map((lang) => (
                      <SelectItem key={lang} value={lang}>
                        {t(`languages.${lang}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              {t('actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" loading={save.isPending}>
              {t('actions.saveChanges')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
