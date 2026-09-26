import { Monitor, Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useTheme, type ThemePreference } from '@/lib/theme'

const OPTIONS: { value: ThemePreference; icon: typeof Sun; key: string }[] = [
  { value: 'light', icon: Sun, key: 'topbar.themeLight' },
  { value: 'dark', icon: Moon, key: 'topbar.themeDark' },
  { value: 'system', icon: Monitor, key: 'topbar.themeSystem' },
]

export function ThemeMenu() {
  const { t } = useTranslation()
  const { theme, resolvedTheme, setTheme } = useTheme()
  const Current = resolvedTheme === 'dark' ? Moon : Sun
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t('topbar.theme')}>
          <Current aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-44">
        <DropdownMenuLabel>{t('topbar.theme')}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme} onValueChange={(value) => setTheme(value as ThemePreference)}>
          {OPTIONS.map(({ value, icon: Icon, key }) => (
            <DropdownMenuRadioItem key={value} value={value}>
              <Icon aria-hidden />
              {t(key)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
