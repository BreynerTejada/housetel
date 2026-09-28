import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { DatePicker } from '@/components/DatePicker'
import { MoneyInput } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { moneyLabel, toCents } from '@/features/finance/money'
import { useAddOpeningBalance } from '../api'

/** "Agregar saldo inicial": an invoice the company still owes from before Housetel (migration of receivables). */
export function OpeningBalanceDialog({
  open,
  onOpenChange,
  companyId,
  companyName,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  companyId: string
  companyName: string
}) {
  const { t } = useTranslation('corporate')
  const { property } = useActiveProperty()
  const add = useAddOpeningBalance(companyId)
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState<string | null>(null)
  const [reference, setReference] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const ready = toCents(amount) > 0 && Boolean(date) && reference.trim().length > 0

  function close(next: boolean) {
    if (add.isPending) return
    if (!next) {
      setAmount('')
      setDate(null)
      setReference('')
      setDescription('')
      setError(null)
    }
    onOpenChange(next)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!ready || !date) return
    setError(null)
    try {
      await add.mutateAsync({ amount, document_date: date, reference: reference.trim(), description: description.trim() })
      toast.success(t('opening.added', { reference: reference.trim(), amount: moneyLabel(amount) }))
      close(false)
    } catch (err) {
      setError(errorMessage(err, t))
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-md" hideClose={add.isPending}>
        <form onSubmit={submit} className="grid gap-4" noValidate>
          <DialogHeader>
            <DialogTitle>{t('opening.title')}</DialogTitle>
            <DialogDescription>{t('opening.description', { company: companyName })}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor="opening-reference">{t('opening.reference')}</Label>
            <Input
              id="opening-reference"
              autoComplete="off"
              placeholder="FV-2024-0891"
              value={reference}
              maxLength={120}
              onChange={(event) => setReference(event.target.value)}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="opening-amount">{t('opening.amount')}</Label>
              <MoneyInput id="opening-amount" value={amount} onChange={setAmount} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="opening-date">{t('opening.date')}</Label>
              <DatePicker id="opening-date" value={date} onChange={setDate} max={property?.business_date} />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="opening-description">{t('opening.descriptionLabel')}</Label>
            <Input
              id="opening-description"
              autoComplete="off"
              value={description}
              maxLength={255}
              placeholder={t('opening.descriptionPlaceholder')}
              onChange={(event) => setDescription(event.target.value)}
            />
            <p className="text-xs text-muted">{t('opening.hint')}</p>
          </div>
          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button variant="secondary" onClick={() => close(false)} disabled={add.isPending}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" disabled={!ready} loading={add.isPending}>
              {t('opening.submit')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
