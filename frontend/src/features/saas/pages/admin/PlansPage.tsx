import { zodResolver } from '@hookform/resolvers/zod'
import { Package, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { FormField } from '@/components/FormField'
import { LoadingState } from '@/components/LoadingState'
import { MoneyInput } from '@/components/Money'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { formatMoney, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useDeletePlan, usePlans, useSavePlan, type Plan } from '../../api'
import { PlanLimits } from '../../components/ChangePlanDialog'
import { pickText } from '../../helpers'

/** `/admin/plans`: the plan catalog (every plan includes every module; plans differ only by size). */
export default function PlansPage() {
  const { t } = useTranslation('saas')
  const plans = usePlans()
  const [editing, setEditing] = useState<Plan | 'new' | null>(null)

  return (
    <div className="mx-auto grid grid-cols-1 w-full max-w-6xl gap-2">
      <PageHeader
        title={t('admin.plans.title')}
        description={t('admin.plans.description')}
        actions={
          <Button variant="primary" onClick={() => setEditing('new')}>
            <Plus aria-hidden />
            {t('admin.plans.new')}
          </Button>
        }
      />
      {plans.isPending ? (
        <LoadingState variant="rows" rows={4} />
      ) : plans.isError ? (
        <ErrorState error={plans.error} onRetry={() => void plans.refetch()} />
      ) : plans.data.length === 0 ? (
        <EmptyState icon={Package} title={t('admin.plans.empty')} />
      ) : (
        <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {plans.data.map((plan) => (
            <PlanCard key={plan.id} plan={plan} onEdit={() => setEditing(plan)} />
          ))}
        </ul>
      )}
      {editing && <PlanFormDialog plan={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

function PlanCard({ plan, onEdit }: { plan: Plan; onEdit: () => void }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const remove = useDeletePlan()
  const yearlyMonthly = Math.round(Number(plan.price_yearly) / 12)
  return (
    <li
      className={cn(
        'relative flex flex-col gap-4 rounded-xl border bg-surface p-5 shadow-xs',
        plan.is_active ? 'border-border' : 'border-dashed border-border-strong opacity-80',
      )}
    >
      <span aria-hidden className="absolute top-4 right-4 size-2.5 rounded-full bg-bg shadow-[inset_0_1px_2px_rgb(0_0_0/0.3)]" />
      <div className="flex flex-wrap items-center gap-2 pr-6">
        <p className="text-[22px] leading-tight font-extrabold tracking-[-0.03em] text-fg">{pickText(plan.name, lang)}</p>
        <Badge tone="outline" className="num">{plan.code}</Badge>
        {!plan.is_active && <Badge tone="stone">{t('admin.plans.inactive')}</Badge>}
      </div>
      <p className="text-sm text-muted">{pickText(plan.description, lang) || '—'}</p>
      <PlanLimits plan={plan} className="text-sm font-medium text-fg" />
      <dl className="grid grid-cols-2 gap-3 rounded-lg bg-surface-2 p-3">
        <div>
          <dt className="text-xs font-semibold text-muted">{t('admin.plans.monthly')}</dt>
          <dd className="num mt-0.5 font-bold text-fg">{formatMoney(plan.price_monthly)}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-muted">{t('admin.plans.yearly')}</dt>
          <dd className="num mt-0.5 font-bold text-fg">{formatMoney(plan.price_yearly)}</dd>
          <dd className="num text-xs text-muted">{t('billing.perYearEq', { amount: formatMoney(yearlyMonthly) })}</dd>
        </div>
      </dl>
      <p className="text-sm text-muted">
        {t('admin.plans.subscriptions', { count: plan.active_subscriptions_count ?? 0, total: plan.subscriptions_count ?? 0 })}
      </p>
      <div className="mt-auto flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" onClick={onEdit}>
          <Pencil aria-hidden />
          {t('common:actions.edit')}
        </Button>
        <ConfirmDialog
          trigger={
            <Button variant="ghost" size="sm" className="text-danger-ink hover:bg-danger-soft">
              <Trash2 aria-hidden />
              {t('common:actions.delete')}
            </Button>
          }
          title={t('admin.plans.deleteTitle', { name: pickText(plan.name, lang) })}
          description={t('admin.plans.deleteText')}
          confirmLabel={t('common:actions.delete')}
          onConfirm={async () => {
            await remove.mutateAsync(plan.id)
            toast.success(t('admin.plans.deleted', { name: pickText(plan.name, lang) }))
          }}
        />
      </div>
    </li>
  )
}

const optionalCount = z
  .string()
  .trim()
  .refine((value) => value === '' || (/^\d+$/.test(value) && Number(value) > 0), 'saas:admin.plans.errors.count')

const schema = z.object({
  code: z.string().trim().regex(/^[a-z0-9][a-z0-9-]{1,39}$/, 'saas:admin.plans.errors.code'),
  name_es: z.string().trim().min(2, 'validation.required'),
  name_en: z.string().trim(),
  description_es: z.string().trim(),
  description_en: z.string().trim(),
  max_units: optionalCount,
  max_properties: optionalCount,
  price_monthly: z.string().refine((value) => value !== '' && Number(value) >= 0, 'validation.required'),
  price_yearly: z.string().refine((value) => value !== '' && Number(value) >= 0, 'validation.required'),
  is_active: z.boolean(),
  sort: z.string().regex(/^\d{1,4}$/, 'validation.number'),
})

type PlanValues = z.infer<typeof schema>

function PlanFormDialog({ plan, onClose }: { plan: Plan | null; onClose: () => void }) {
  const { t } = useTranslation('saas')
  const save = useSavePlan()
  const [failure, setFailure] = useState<string | null>(null)
  const form = useForm<PlanValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      code: plan?.code ?? '',
      name_es: plan?.name.es ?? '',
      name_en: plan?.name.en ?? '',
      description_es: plan?.description.es ?? '',
      description_en: plan?.description.en ?? '',
      max_units: plan?.max_units ? String(plan.max_units) : '',
      max_properties: plan?.max_properties ? String(plan.max_properties) : '',
      price_monthly: plan ? String(Math.round(Number(plan.price_monthly))) : '',
      price_yearly: plan ? String(Math.round(Number(plan.price_yearly))) : '',
      is_active: plan?.is_active ?? true,
      sort: String(plan?.sort ?? 40),
    },
  })

  function yearlyFromMonthly() {
    const monthly = Number(form.getValues('price_monthly'))
    if (monthly > 0) form.setValue('price_yearly', String(Math.round(monthly * 12 * 0.85)), { shouldValidate: true })
  }

  async function onSubmit(values: PlanValues) {
    setFailure(null)
    try {
      await save.mutateAsync({
        id: plan?.id,
        code: values.code,
        name: { es: values.name_es, en: values.name_en || values.name_es },
        description: { es: values.description_es, en: values.description_en },
        max_units: values.max_units ? Number(values.max_units) : null,
        max_properties: values.max_properties ? Number(values.max_properties) : null,
        price_monthly: values.price_monthly,
        price_yearly: values.price_yearly,
        is_active: values.is_active,
        sort: Number(values.sort),
      })
      toast.success(plan ? t('admin.plans.saved') : t('admin.plans.created'))
      onClose()
    } catch (error) {
      if (isApiError(error) && error.fields) {
        for (const [field, messages] of Object.entries(error.fields)) {
          const key = (field === 'name' ? 'name_es' : field === 'description' ? 'description_es' : field) as keyof PlanValues
          if (key in schema.shape) form.setError(key, { message: messages[0] })
        }
      }
      setFailure(errorMessage(error, t))
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && !save.isPending && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{plan ? t('admin.plans.editTitle') : t('admin.plans.newTitle')}</DialogTitle>
          <DialogDescription>{t('admin.plans.formHint')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="grid grid-cols-1 gap-4" noValidate>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField
              control={form.control}
              name="name_es"
              label={t('admin.plans.nameEs')}
              render={({ field, ...a11y }) => <Input {...field} {...a11y} />}
            />
            <FormField
              control={form.control}
              name="name_en"
              label={t('admin.plans.nameEn')}
              render={({ field, ...a11y }) => <Input {...field} {...a11y} />}
            />
            <FormField
              control={form.control}
              name="description_es"
              label={t('admin.plans.descriptionEs')}
              render={({ field, ...a11y }) => <Textarea rows={2} {...field} {...a11y} />}
            />
            <FormField
              control={form.control}
              name="description_en"
              label={t('admin.plans.descriptionEn')}
              render={({ field, ...a11y }) => <Textarea rows={2} {...field} {...a11y} />}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <FormField
              control={form.control}
              name="code"
              label={t('admin.plans.code')}
              description={plan ? t('admin.plans.codeLocked') : t('admin.plans.codeHint')}
              render={({ field, ...a11y }) => <Input className="num" disabled={Boolean(plan)} {...field} {...a11y} />}
            />
            <FormField
              control={form.control}
              name="max_units"
              label={t('admin.plans.maxUnits')}
              description={t('admin.plans.unlimitedHint')}
              render={({ field, ...a11y }) => <Input inputMode="numeric" className="num" {...field} {...a11y} />}
            />
            <FormField
              control={form.control}
              name="max_properties"
              label={t('admin.plans.maxProperties')}
              description={t('admin.plans.unlimitedHint')}
              render={({ field, ...a11y }) => <Input inputMode="numeric" className="num" {...field} {...a11y} />}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <FormField
              control={form.control}
              name="price_monthly"
              label={t('admin.plans.monthly')}
              render={({ field, ...a11y }) => (
                <MoneyInput name={field.name} value={field.value} onChange={field.onChange} onBlur={field.onBlur} {...a11y} />
              )}
            />
            <FormField
              control={form.control}
              name="price_yearly"
              label={t('admin.plans.yearly')}
              description={
                <button type="button" onClick={yearlyFromMonthly} className="font-semibold text-accent-ink underline underline-offset-4">
                  {t('admin.plans.yearlyFromMonthly')}
                </button>
              }
              render={({ field, ...a11y }) => (
                <MoneyInput name={field.name} value={field.value} onChange={field.onChange} onBlur={field.onBlur} {...a11y} />
              )}
            />
            <FormField
              control={form.control}
              name="sort"
              label={t('admin.plans.sort')}
              render={({ field, ...a11y }) => <Input inputMode="numeric" className="num" {...field} {...a11y} />}
            />
          </div>
          <Controller
            control={form.control}
            name="is_active"
            render={({ field }) => (
              <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
                <div>
                  <Label htmlFor="plan-active" className="font-semibold text-fg">
                    {t('admin.plans.active')}
                  </Label>
                  <p className="text-xs text-muted">{t('admin.plans.activeHint')}</p>
                </div>
                <Switch id="plan-active" name={field.name} checked={field.value} onCheckedChange={field.onChange} />
              </div>
            )}
          />
          {failure && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {failure}
            </p>
          )}
          <DialogFooter>
            <Button variant="secondary" onClick={onClose} disabled={save.isPending}>
              {t('common:actions.cancel')}
            </Button>
            <Button type="submit" variant="primary" loading={save.isPending}>
              {plan ? t('common:actions.saveChanges') : t('admin.plans.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
