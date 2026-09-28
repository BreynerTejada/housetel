import { Ban, CircleCheck, CreditCard, MoreHorizontal } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog, DangerConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/errors'
import { formatMoney } from '@/lib/format'
import { useChargeInvoice, useMarkInvoicePaid, useVoidInvoice, type PlatformInvoice } from '../api'

/** Row actions of a platform invoice for the super-admin: charge now, mark as paid (manual) and void. */
export function AdminInvoiceActions({ invoice, onChanged }: { invoice: PlatformInvoice; onChanged?: () => void }) {
  const { t } = useTranslation('saas')
  const charge = useChargeInvoice()
  const markPaid = useMarkInvoicePaid()
  const voidInvoice = useVoidInvoice()
  const [dialog, setDialog] = useState<'paid' | 'void' | null>(null)
  const [reference, setReference] = useState('')
  const [reason, setReason] = useState('')
  const unpaid = invoice.status === 'open' || invoice.status === 'failed'
  if (!unpaid) return null

  async function chargeNow() {
    try {
      const result = (await charge.mutateAsync({ id: invoice.id })) as { status?: string; message?: string }
      if (result.status === 'approved') toast.success(t('admin.invoices.charged', { number: invoice.number }))
      else if (result.status === 'requires_action') toast.warning(result.message || t('admin.invoices.noCard'))
      else toast.error(result.message || t('billing.pay.declined'))
      onChanged?.()
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  return (
    // Portaled menus and dialogs still bubble React events to the table row: keep them here.
    <span className="contents" onClick={(event) => event.stopPropagation()}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t('admin.invoices.actionsFor', { number: invoice.number })}
            loading={charge.isPending}
            onClick={(event) => event.stopPropagation()}
          >
            <MoreHorizontal aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" onClick={(event) => event.stopPropagation()}>
          <DropdownMenuItem onSelect={() => void chargeNow()}>
            <CreditCard aria-hidden />
            {t('admin.invoices.charge')}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setDialog('paid')}>
            <CircleCheck aria-hidden />
            {t('admin.invoices.markPaid')}
          </DropdownMenuItem>
          <DropdownMenuItem destructive onSelect={() => setDialog('void')}>
            <Ban aria-hidden />
            {t('admin.invoices.void')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog
        open={dialog === 'paid'}
        onOpenChange={(open) => {
          setDialog(open ? 'paid' : null)
          if (!open) setReference('')
        }}
        title={t('admin.invoices.markPaidTitle', { number: invoice.number })}
        description={t('admin.invoices.markPaidText', { amount: formatMoney(invoice.total), org: invoice.organization.name })}
        confirmLabel={t('admin.invoices.markPaid')}
        onConfirm={async () => {
          await markPaid.mutateAsync({ id: invoice.id, confirm: true, reference: reference.trim() || undefined })
          toast.success(t('admin.invoices.markedPaid', { number: invoice.number }))
          onChanged?.()
        }}
      >
        <div className="grid grid-cols-1 gap-1.5">
          <Label htmlFor={`paid-ref-${invoice.id}`}>{t('admin.invoices.reference')}</Label>
          <Input
            id={`paid-ref-${invoice.id}`}
            name="reference"
            value={reference}
            placeholder={t('admin.invoices.referencePlaceholder')}
            onChange={(event) => setReference(event.target.value)}
          />
        </div>
      </ConfirmDialog>

      <DangerConfirmDialog
        open={dialog === 'void'}
        onOpenChange={(open) => {
          setDialog(open ? 'void' : null)
          if (!open) setReason('')
        }}
        title={t('admin.invoices.voidTitle', { number: invoice.number })}
        description={t('admin.invoices.voidText')}
        confirmLabel={t('admin.invoices.void')}
        confirmText={invoice.number}
        onConfirm={async () => {
          await voidInvoice.mutateAsync({ id: invoice.id, confirm: true, reason: reason.trim() })
          toast.success(t('admin.invoices.voided', { number: invoice.number }))
          onChanged?.()
        }}
      >
        <div className="grid grid-cols-1 gap-1.5">
          <Label htmlFor={`void-reason-${invoice.id}`}>{t('admin.invoices.voidReason')}</Label>
          <Textarea id={`void-reason-${invoice.id}`} name="reason" rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
        </div>
      </DangerConfirmDialog>
    </span>
  )
}
