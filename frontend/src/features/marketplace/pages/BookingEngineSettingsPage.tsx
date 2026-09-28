import { useQuery } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { getEngineSettings, getListingSettings, marketplaceKeys } from '../api'
import { EmbedPanel } from '../components/settings/EmbedPanel'
import { EngineSettingsForm } from '../components/settings/EngineSettingsForm'
import { ListingForm } from '../components/settings/ListingForm'

const TABS = ['engine', 'listing', 'embed'] as const
type Tab = (typeof TABS)[number]

function ListingTab() {
  const listing = useQuery({ queryKey: marketplaceKeys.listingSettings, queryFn: getListingSettings })
  if (listing.isPending) return <LoadingState />
  if (listing.isError) return <ErrorState error={listing.error} onRetry={() => void listing.refetch()} />
  return <ListingForm key={JSON.stringify(listing.data)} listing={listing.data} />
}

/** `/app/settings/booking-engine` (`marketplace.manage`): the hotel's booking page, its marketplace listing and the widget. */
export default function BookingEngineSettingsPage() {
  const { t } = useTranslation('marketplace')
  const [params, setParams] = useSearchParams()
  const tab: Tab = (TABS as readonly string[]).includes(params.get('tab') ?? '') ? (params.get('tab') as Tab) : 'engine'
  const engine = useQuery({ queryKey: marketplaceKeys.engineSettings, queryFn: getEngineSettings })

  return (
    <div>
      <PageHeader
        title={t('settings.title')}
        description={t('settings.description')}
        actions={
          engine.data && (
            <Button asChild>
              <a href={engine.data.public_url} target="_blank" rel="noopener noreferrer">
                {t('settings.viewPage')}
                <ExternalLink aria-hidden />
              </a>
            </Button>
          )
        }
      />
      {engine.isPending ? (
        <LoadingState />
      ) : engine.isError ? (
        <ErrorState error={engine.error} onRetry={() => void engine.refetch()} />
      ) : (
        <Tabs value={tab} onValueChange={(value) => setParams(value === 'engine' ? {} : { tab: value }, { replace: true })}>
          <TabsList>
            {TABS.map((value) => (
              <TabsTrigger key={value} value={value}>
                {t(`settings.tabs.${value}`)}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="engine" className="pt-6">
            <EngineSettingsForm key={JSON.stringify(engine.data)} settings={engine.data} />
          </TabsContent>
          <TabsContent value="listing" className="pt-6">
            <ListingTab />
          </TabsContent>
          <TabsContent value="embed" className="pt-6">
            <EmbedPanel settings={engine.data} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}
