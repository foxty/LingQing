import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Languages } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export default function LanguageSwitcher() {
  const { t, i18n } = useTranslation()

  const languages = [
    { code: 'zh', label: t('language.zh') },
    { code: 'en', label: t('language.en') },
  ]

  const current = languages.find((lang) => i18n.language.startsWith(lang.code)) ?? languages[0]

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-11 gap-1.5 px-2.5" title={t('language.switchTo')}>
          <Languages className="w-4 h-4" />
          <span className="text-sm font-medium">{current.label}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {languages.map((lang) => (
          <DropdownMenuItem
            key={lang.code}
            onClick={() => i18n.changeLanguage(lang.code)}
            className={i18n.language.startsWith(lang.code) ? 'font-medium' : ''}
          >
            {lang.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
