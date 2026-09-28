import { Sparkles } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Tooltip } from '@/components/ui/tooltip'
import { useHotkey } from '@/lib/hooks'
import { useCopilotStore } from '../store'

const CopilotPanel = lazy(() => import('./CopilotPanel'))

/** Topbar button (and ⌘J / Ctrl+J) that opens the copilot; the panel's code loads on first use. */
export function CopilotButton() {
  const { t } = useTranslation('ai')
  const open = useCopilotStore((state) => state.open)
  const setOpen = useCopilotStore((state) => state.setOpen)
  const toggle = useCopilotStore((state) => state.toggle)
  // The panel mounts the first time it opens and then stays mounted (keeps its scroll and draft).
  const [mounted, setMounted] = useState(open)
  if (open && !mounted) setMounted(true)
  useHotkey('j', toggle, { mod: true })

  return (
    <>
      <Tooltip content={`${t('copilot.buttonLabel')} · ${t('copilot.shortcut')}`}>
        <Button variant="ghost" size="sm" aria-label={t('copilot.buttonLabel')} onClick={() => setOpen(true)} className="gap-1.5 px-2 sm:px-2.5">
          <Sparkles aria-hidden className="text-accent-ink" />
          <span className="hidden md:inline">{t('copilot.button')}</span>
        </Button>
      </Tooltip>
      {mounted && (
        <Suspense fallback={null}>
          <CopilotPanel open={open} onOpenChange={setOpen} />
        </Suspense>
      )}
    </>
  )
}
