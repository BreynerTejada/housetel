import { Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { checkPassword, MIN_PASSWORD } from '../password'

/**
 * Live checklist under a new password: the rules the browser can verify. Referenced from the password
 * input with `aria-describedby`, so it is read with the field instead of announced on every keystroke.
 */
export function PasswordRules({ id, password, confirm }: { id: string; password: string; confirm: string }) {
  const { t } = useTranslation('team')
  const check = checkPassword(password, confirm)
  const rules = [
    { key: 'length', ok: check.length, label: t('password.rules.length', { min: MIN_PASSWORD }) },
    { key: 'numbers', ok: check.notOnlyNumbers, label: t('password.rules.notOnlyNumbers') },
    { key: 'match', ok: check.matches, label: t('password.rules.match') },
  ]
  return (
    <ul id={id} className="grid gap-1.5 text-xs">
      {rules.map((rule) => (
        <li key={rule.key} className={cn('flex items-center gap-2 transition-colors', rule.ok ? 'text-success-ink' : 'text-muted')}>
          <span
            aria-hidden
            className={cn(
              'grid size-4 shrink-0 place-items-center rounded-full border transition-colors',
              rule.ok ? 'border-transparent bg-success-soft' : 'border-border-strong',
            )}
          >
            {rule.ok && <Check className="size-3" strokeWidth={3} />}
          </span>
          <span>
            {rule.label}
            <span className="sr-only"> · {rule.ok ? t('password.rules.met') : t('password.rules.pending')}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}
