import { useMutation } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { AMENITY_CATEGORIES, useInvalidateInventory, type Amenity, type AmenityCategory, type I18nText } from '../api'
import { AMENITY_ICON_NAMES, amenityIcon } from '../lib/amenityIcons'
import { I18nTextInput } from './I18nTextInput'

/** An amenity the global catalog does not have, only for this organization. */
export function AmenityCreateDialog({ onCreated }: { onCreated: (amenity: Amenity) => void }) {
  const { t } = useTranslation('inventory')
  const invalidate = useInvalidateInventory()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState<I18nText>({})
  const [category, setCategory] = useState<AmenityCategory>('room')
  const [icon, setIcon] = useState('sparkles')
  const [error, setError] = useState<string | null>(null)
  const categoryId = useId()
  const iconsId = useId()

  const create = useMutation({
    mutationFn: () => api.post<Amenity>('/inventory/amenities/', { code: name.es || name.en || '', name, icon, category }),
    onSuccess: (amenity) => {
      toast.success(t('amenities.created'))
      void invalidate()
      onCreated(amenity)
      setOpen(false)
      setName({})
      setError(null)
    },
    onError: (err) => setError(errorMessage(err, t)),
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="subtle" size="sm">
          <Plus aria-hidden />
          {t('amenities.create')}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (name.es || name.en) create.mutate()
          }}
        >
          <DialogHeader>
            <DialogTitle>{t('amenities.createTitle')}</DialogTitle>
            <DialogDescription>{t('amenities.createDescription')}</DialogDescription>
          </DialogHeader>
          <I18nTextInput label={t('fields.name')} name="name" value={name} onChange={setName} />
          <div className="grid gap-1.5">
            <span id={categoryId} className="text-[13px] font-semibold">
              {t('amenities.category')}
            </span>
            <Select name="category" value={category} onValueChange={(value) => setCategory(value as AmenityCategory)}>
              <SelectTrigger aria-labelledby={categoryId}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AMENITY_CATEGORIES.map((item) => (
                  <SelectItem key={item} value={item}>
                    {t(`amenityCategories.${item}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <fieldset className="grid gap-1.5">
            <legend id={iconsId} className="mb-1.5 text-[13px] font-semibold">
              {t('amenities.icon')}
            </legend>
            <div role="radiogroup" aria-labelledby={iconsId} className="grid max-h-40 grid-cols-8 gap-1 overflow-y-auto rounded-lg border border-border p-2">
              {AMENITY_ICON_NAMES.map((iconName) => {
                const Icon = amenityIcon(iconName)
                return (
                  <button
                    key={iconName}
                    type="button"
                    role="radio"
                    aria-checked={icon === iconName}
                    aria-label={iconName}
                    onClick={() => setIcon(iconName)}
                    className={cn(
                      'grid size-8 place-items-center rounded-md text-muted transition-colors hover:bg-surface-2 hover:text-fg',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
                      icon === iconName && 'bg-accent-soft text-accent-ink',
                    )}
                  >
                    <Icon aria-hidden className="size-4" />
                  </button>
                )
              })}
            </div>
          </fieldset>
          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" disabled={!name.es && !name.en} loading={create.isPending}>
              {t('amenities.createSubmit')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
