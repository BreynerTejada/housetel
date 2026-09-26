import { useTranslation } from 'react-i18next'
import { Toaster as Sonner } from 'sonner'
import { useTheme } from '@/lib/theme'

/**
 * App-wide toasts (mounted once in AppProviders). Trigger them with `toast` from 'sonner':
 * `toast.success(t('...'))`, `toast.error(message)`.
 */
export function Toaster() {
  const { t } = useTranslation()
  const { resolvedTheme } = useTheme()
  return (
    <Sonner
      theme={resolvedTheme}
      containerAriaLabel={t('toasts.region')}
      position="bottom-right"
      closeButton
      toastOptions={{
        classNames: {
          toast:
            'group !rounded-lg !border !border-border !bg-surface !text-fg !shadow-md !font-sans !text-sm',
          description: '!text-muted',
          actionButton: '!bg-accent !text-on-accent !rounded-md !font-semibold',
          cancelButton: '!bg-surface-2 !text-fg !rounded-md',
          closeButton: '!bg-surface !border-border !text-muted',
          success: '[&_[data-icon]]:!text-success',
          error: '[&_[data-icon]]:!text-danger',
          warning: '[&_[data-icon]]:!text-warning',
          info: '[&_[data-icon]]:!text-info',
        },
      }}
    />
  )
}
