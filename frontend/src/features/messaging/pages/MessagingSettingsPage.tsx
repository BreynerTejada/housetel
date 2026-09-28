import { Lock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { PageHeader } from '@/components/PageHeader'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useCan } from '@/lib/permissions'
import { LifecycleRules } from '../components/settings/LifecycleRules'
import { TemplatesPanel } from '../components/settings/TemplatesPanel'

type Tab = 'templates' | 'rules'

/**
 * `/app/settings/messaging`: what Housetel writes to the guests (templates by channel and language) and when
 * it does it on its own (the automatic messages of the guest's journey). Tab and template live in the URL.
 */
export default function MessagingSettingsPage() {
  const { t } = useTranslation('messaging')
  const [params, setParams] = useSearchParams()
  const tab: Tab = params.get('tab') === 'rules' ? 'rules' : 'templates'
  const canEdit = useCan('messaging.templates')

  function openTab(value: string) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value === 'rules') next.set('tab', 'rules')
        else next.delete('tab')
        return next
      },
      { replace: true },
    )
  }

  return (
    <div className="grid gap-2">
      <PageHeader title={t('settings.title')} description={t('settings.description')} />
      {!canEdit && (
        <p className="mb-2 flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2 text-[13px] text-muted">
          <Lock aria-hidden className="size-4 shrink-0" />
          {t('settings.readOnly')}
        </p>
      )}
      <Tabs value={tab} onValueChange={openTab}>
        <TabsList>
          <TabsTrigger value="templates">{t('settings.tabs.templates')}</TabsTrigger>
          <TabsTrigger value="rules">{t('settings.tabs.rules')}</TabsTrigger>
        </TabsList>
        <TabsContent value="templates">
          <TemplatesPanel canEdit={canEdit} />
        </TabsContent>
        <TabsContent value="rules">
          <LifecycleRules canEdit={canEdit} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
