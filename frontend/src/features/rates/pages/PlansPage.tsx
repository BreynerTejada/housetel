import { CalendarRange, Layers, Tags } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useActiveProperty } from '@/lib/auth'
import { DefaultsPanel } from '../components/plans/DefaultsPanel'
import { PlanFamilies } from '../components/plans/PlanFamilies'
import { SeasonsPanel } from '../components/plans/SeasonsPanel'
import { usePlansData } from '../hooks/usePlansData'

const TABS = ['plans', 'defaults', 'seasons'] as const
type Tab = (typeof TABS)[number]

/**
 * `/app/rates/plans`: how prices are built. Base plans carry the default price of each category, derived plans
 * follow them by a percentage or an amount, and seasons replace the default price between two dates.
 */
export default function PlansPage() {
  const { t } = useTranslation('rates')
  const { property } = useActiveProperty()
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab')
  const tab: Tab = (TABS as readonly string[]).includes(requested ?? '') ? (requested as Tab) : 'plans'
  const data = usePlansData()

  function changeTab(value: string) {
    setParams(value === 'plans' ? {} : { tab: value }, { replace: true })
  }

  return (
    <div>
      <PageHeader title={t('plans.title')} description={t('plans.description')} />
      {!property ? (
        <LoadingState variant="rows" rows={6} />
      ) : (
        <Tabs value={tab} onValueChange={changeTab}>
          {/* icons only from sm up: the three tabs fit a 375 px phone without scrolling */}
          <TabsList aria-label={t('plans.title')}>
            <TabsTrigger value="plans">
              <Layers aria-hidden className="hidden sm:block" />
              {t('plans.tabs.plans')}
            </TabsTrigger>
            <TabsTrigger value="defaults">
              <Tags aria-hidden className="hidden sm:block" />
              {t('plans.tabs.defaults')}
            </TabsTrigger>
            <TabsTrigger value="seasons">
              <CalendarRange aria-hidden className="hidden sm:block" />
              {t('plans.tabs.seasons')}
            </TabsTrigger>
          </TabsList>
          <TabsContent value="plans">
            <PlanFamilies data={data} currency={property.currency} />
          </TabsContent>
          <TabsContent value="defaults">
            <DefaultsPanel data={data} currency={property.currency} />
          </TabsContent>
          <TabsContent value="seasons">
            <SeasonsPanel data={data} currency={property.currency} today={property.business_date} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}
