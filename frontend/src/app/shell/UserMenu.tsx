import { useQueryClient } from '@tanstack/react-query'
import { Gauge, Hotel, Languages, LogOut, Monitor, Moon, Sun, UserRound } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Avatar, AvatarFallback, initials } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useLogout, useMe } from '@/lib/auth'
import { useMediaQuery } from '@/lib/hooks'
import { currentLanguage, isLanguage, LANGUAGES, setLanguage } from '@/lib/i18n'
import { useTheme, type ThemePreference } from '@/lib/theme'

const ProfileDialog = lazy(() => import('./ProfileDialog').then((m) => ({ default: m.ProfileDialog })))

export function UserMenu({ area = 'app' }: { area?: 'app' | 'admin' }) {
  const { t } = useTranslation()
  const { data: me } = useMe()
  const logout = useLogout()
  const queryClient = useQueryClient()
  const { theme, setTheme } = useTheme()
  const isPhone = useMediaQuery('(max-width: 639px)')
  const [profileOpen, setProfileOpen] = useState(false)
  const [profileMounted, setProfileMounted] = useState(false)
  if (!me) return null
  const hasHotel = me.memberships.some((membership) => membership.properties.length > 0)

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={t('topbar.userMenu')}
            className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
          >
            <Avatar>
              <AvatarFallback>{initials(me.full_name, me.email)}</AvatarFallback>
            </Avatar>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <div className="px-2 py-2">
            <p className="truncate text-sm font-bold text-fg">{me.full_name || me.email}</p>
            <p className="truncate text-xs text-muted">{me.email}</p>
          </div>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => {
              setProfileMounted(true)
              setProfileOpen(true)
            }}
          >
            <UserRound aria-hidden />
            {t('topbar.profile')}
          </DropdownMenuItem>
          {isPhone && (
            <>
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>
                  <Languages aria-hidden />
                  {t('topbar.language')}
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent>
                  <DropdownMenuRadioGroup
                    value={currentLanguage()}
                    onValueChange={(value) => isLanguage(value) && void setLanguage(value, queryClient)}
                  >
                    {LANGUAGES.map((lang) => (
                      <DropdownMenuRadioItem key={lang} value={lang} lang={lang}>
                        {t(`languages.${lang}`)}
                      </DropdownMenuRadioItem>
                    ))}
                  </DropdownMenuRadioGroup>
                </DropdownMenuSubContent>
              </DropdownMenuSub>
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>
                  {theme === 'dark' ? <Moon aria-hidden /> : theme === 'light' ? <Sun aria-hidden /> : <Monitor aria-hidden />}
                  {t('topbar.theme')}
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent>
                  <DropdownMenuRadioGroup value={theme} onValueChange={(value) => setTheme(value as ThemePreference)}>
                    <DropdownMenuRadioItem value="light">{t('topbar.themeLight')}</DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="dark">{t('topbar.themeDark')}</DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="system">{t('topbar.themeSystem')}</DropdownMenuRadioItem>
                  </DropdownMenuRadioGroup>
                </DropdownMenuSubContent>
              </DropdownMenuSub>
            </>
          )}
          {area === 'app' && me.is_platform_admin && (
            <DropdownMenuItem asChild>
              <Link to="/admin">
                <Gauge aria-hidden />
                {t('topbar.platformPanel')}
              </Link>
            </DropdownMenuItem>
          )}
          {area === 'admin' && hasHotel && (
            <DropdownMenuItem asChild>
              <Link to="/app">
                <Hotel aria-hidden />
                {t('topbar.backToHotel')}
              </Link>
            </DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => logout.mutate()}
          >
            <LogOut aria-hidden />
            {t('actions.logout')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {profileMounted && (
        <Suspense fallback={null}>
          <ProfileDialog open={profileOpen} onOpenChange={setProfileOpen} />
        </Suspense>
      )}
    </>
  )
}
