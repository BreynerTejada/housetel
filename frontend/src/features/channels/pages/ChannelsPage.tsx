import { FlaskConical, Network, Plus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useActiveProperty } from '@/lib/auth'
import { useCan } from '@/lib/permissions'
import { useRuntimeConfig } from '@/lib/runtime'
import { useChannelOptions, useConnections, type ChannelCode, type ChannelOptions, type Connection } from '../api'
import { AriQueuePanel } from '../components/AriQueuePanel'
import { ChannelMark } from '../components/ChannelMark'
import { ConnectionCard } from '../components/ConnectionCard'
import { ConnectionWizard } from '../components/ConnectionWizard'
import { SyncLogPanel } from '../components/SyncLogPanel'

type Tab = 'connections' | 'log' | 'queue'
const TABS: Tab[] = ['connections', 'log', 'queue']
const CHANNEL_ORDER: ChannelCode[] = ['booksim', 'airsim', 'ical', 'channex']

interface WizardState {
  open: boolean
  /** New key on every opening: the wizard starts from its props. */
  key: number
  channel: ChannelCode | null
  editing: Connection | null
}

/**
 * `/app/channels`: the channel manager. Every connected channel with the state of both directions (prices out,
 * bookings in), the wizard to connect one, the sync log and the ARI queue. Starts over when the property changes.
 */
export default function ChannelsPage() {
  const { property } = useActiveProperty()
  if (!property) return <LoadingState variant="rows" rows={6} />
  return <Channels key={property.id} />
}

function Channels() {
  const { t } = useTranslation('channels')
  const canManage = useCan('distribution.manage')
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab') as Tab | null
  const tab: Tab = requested && TABS.includes(requested) ? requested : 'connections'
  const connectionsQuery = useConnections({ refetchInterval: 15_000 })
  const optionsQuery = useChannelOptions()
  const [wizard, setWizard] = useState<WizardState>({ open: false, key: 0, channel: null, editing: null })

  const connections = connectionsQuery.data ?? []
  const options = optionsQuery.data
  const errors = connections.reduce((sum, item) => sum + item.stats.errors_24h, 0)
  const queued = connections.reduce((sum, item) => sum + item.stats.pending_updates + item.stats.failed_updates, 0)
  const { simulations_enabled: simulations } = useRuntimeConfig()
  // the OTA simulator is a development/demo tool: never offered where simulations are off (production)
  const hasSimulated = simulations && connections.some((item) => item.simulated)

  function openWizard(channel: ChannelCode | null, editing: Connection | null = null) {
    if (!options) return
    setWizard((current) => ({ open: true, key: current.key + 1, channel, editing }))
  }

  function selectTab(value: string) {
    const next = new URLSearchParams(params)
    if (value === 'connections') next.delete('tab')
    else next.set('tab', value)
    setParams(next, { replace: true })
  }

  return (
    <div className="grid gap-2">
      <PageHeader
        title={t('page.title')}
        description={t('page.description')}
        actions={
          canManage && (
            <>
              {hasSimulated && (
                <Button asChild>
                  <Link to="/app/simulators/ota">
                    <FlaskConical aria-hidden /> {t('page.openSimulator')}
                  </Link>
                </Button>
              )}
              <Button variant="primary" onClick={() => openWizard(null)} disabled={!options}>
                <Plus aria-hidden /> {t('page.connect')}
              </Button>
            </>
          )
        }
      />

      <Tabs value={tab} onValueChange={selectTab}>
        <TabsList aria-label={t('page.sections')}>
          <TabsTrigger value="connections">
            {t('tabs.connections')}
            {connections.length > 0 && <Badge tone="neutral">{connections.length}</Badge>}
          </TabsTrigger>
          <TabsTrigger value="log">
            {t('tabs.log')}
            {errors > 0 && <Badge tone="danger">{errors}</Badge>}
          </TabsTrigger>
          <TabsTrigger value="queue">
            {t('tabs.queue')}
            {queued > 0 && <Badge tone="warning">{queued}</Badge>}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="connections">
          {connectionsQuery.isPending ? (
            <LoadingState variant="rows" rows={6} />
          ) : connectionsQuery.isError && !connectionsQuery.data ? (
            <ErrorState error={connectionsQuery.error} onRetry={() => void connectionsQuery.refetch()} />
          ) : connections.length === 0 ? (
            <EmptyState
              icon={Network}
              title={t('page.emptyTitle')}
              description={t('page.emptyHint')}
              action={
                canManage && (
                  <Button variant="primary" onClick={() => openWizard(null)} disabled={!options}>
                    <Plus aria-hidden /> {t('page.connect')}
                  </Button>
                )
              }
            />
          ) : (
            <div className="grid items-start gap-4 lg:grid-cols-2 2xl:grid-cols-3">
              {connections.map((connection) => (
                <ConnectionCard
                  key={connection.id}
                  connection={connection}
                  canManage={canManage}
                  onEdit={(item) => openWizard(item.channel_code, item)}
                />
              ))}
              {canManage && options && <AddChannelTile options={options} onPick={(code) => openWizard(code)} />}
            </div>
          )}
        </TabsContent>

        <TabsContent value="log">
          <SyncLogPanel connections={connections} />
        </TabsContent>

        <TabsContent value="queue">
          <AriQueuePanel connections={connections} canManage={canManage} />
        </TabsContent>
      </Tabs>

      {options && (
        <ConnectionWizard
          key={wizard.key}
          open={wizard.open}
          onOpenChange={(open) => setWizard((current) => ({ ...current, open }))}
          options={options}
          channel={wizard.channel}
          editing={wizard.editing}
        />
      )}
    </div>
  )
}

/** The channels this property can still connect, one click from the wizard. */
function AddChannelTile({ options, onPick }: { options: ChannelOptions; onPick: (code: ChannelCode) => void }) {
  const { t } = useTranslation('channels')
  const available = CHANNEL_ORDER.map((code) => options.channels.find((item) => item.code === code)).filter(
    (item): item is ChannelOptions['channels'][number] => Boolean(item && (!item.connected || item.multiple)),
  )
  if (!available.length) return null
  return (
    <section
      aria-label={t('page.addAnother')}
      className="grid content-start gap-3 rounded-xl border border-dashed border-border-strong bg-surface-2/40 p-5"
    >
      <div>
        <h3 className="text-[15px] leading-6 font-bold tracking-[-0.01em]">{t('page.addAnother')}</h3>
        <p className="text-[13px] text-muted">{t('page.addAnotherHint')}</p>
      </div>
      <ul className="grid gap-2">
        {available.map((item) => (
          <li key={item.code}>
            <button
              type="button"
              onClick={() => onPick(item.code)}
              className="flex w-full items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2.5 text-left transition-colors hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
            >
              <ChannelMark channel={item.code} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-semibold text-fg">{t(`channels.${item.code}.name`)}</span>
                <span className="block truncate text-xs text-muted">{t(`channels.${item.code}.short`)}</span>
              </span>
              <Plus aria-hidden className="size-4 text-muted" />
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
