import { Gauge, LogOut } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/button'
import { useLogout, useMe } from '@/lib/auth'

/** A signed-in user without any property: say what to do instead of showing an empty app. */
export function NoProperties() {
  const { t } = useTranslation()
  const { data: me } = useMe()
  const logout = useLogout()
  return (
    <div className="app-shell grid min-h-dvh place-items-center bg-bg p-6">
      <div className="w-full max-w-md rounded-xl border border-border bg-surface p-8 shadow-sm">
        <Logo />
        <h1 className="mt-8 text-xl text-fg">{t('noProperties.title')}</h1>
        <p className="mt-2 text-muted">{t('noProperties.description')}</p>
        <div className="mt-6 flex flex-wrap gap-2">
          {me?.is_platform_admin && (
            <Button asChild variant="primary">
              <Link to="/admin">
                <Gauge aria-hidden />
                {t('topbar.platformPanel')}
              </Link>
            </Button>
          )}
          <Button
            variant="secondary"
            loading={logout.isPending}
            onClick={() => logout.mutate()}
          >
            <LogOut aria-hidden />
            {t('actions.logout')}
          </Button>
        </div>
      </div>
    </div>
  )
}
