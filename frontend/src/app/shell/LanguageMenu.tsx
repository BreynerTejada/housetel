import { useQueryClient } from '@tanstack/react-query'
import { Languages } from 'lucide-react'
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
import { currentLanguage, isLanguage, LANGUAGES, setLanguage } from '@/lib/i18n'

export function LanguageMenu() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t('topbar.language')}>
          <Languages aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-40">
        <DropdownMenuLabel>{t('topbar.language')}</DropdownMenuLabel>
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
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
