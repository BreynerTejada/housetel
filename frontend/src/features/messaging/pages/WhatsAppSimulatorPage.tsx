import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, Phone, Search, SmartphoneNfc } from 'lucide-react'
import { useEffect, useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import {
  getSimulatorContacts,
  getSimulatorThread,
  messagingKeys,
  postSimulatorInbound,
  type SimulatorContact,
} from '../api'
import { PhoneMockup } from '../components/PhoneMockup'

interface Chosen {
  phone: string
  name: string
  /** A guest of the hotel's organization (its name comes from the CRM, not from WhatsApp). */
  known: boolean
}

/**
 * `/app/simulators/whatsapp`: the staff plays a guest on a phone. Messages go through the same path as a
 * real WhatsApp webhook (the inbox receives them) and the hotel's replies show up on the phone.
 */
export default function WhatsAppSimulatorPage() {
  const { t } = useTranslation('messaging')
  const { property } = useActiveProperty()
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [chosen, setChosen] = useState<Chosen | null>(null)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query.trim()), 300)
    return () => window.clearTimeout(id)
  }, [query])

  const contacts = useQuery({
    queryKey: messagingKeys.simulatorContacts(debounced),
    queryFn: () => getSimulatorContacts(debounced),
  })
  const thread = useQuery({
    queryKey: messagingKeys.simulatorThread(chosen?.phone ?? ''),
    queryFn: () => getSimulatorThread(chosen!.phone),
    enabled: Boolean(chosen),
    refetchInterval: 2_500,
  })
  const enabled = contacts.data?.simulator_enabled ?? thread.data?.simulator_enabled ?? true

  async function send(body: string) {
    if (!chosen) return
    setSending(true)
    try {
      await postSimulatorInbound({ phone: chosen.phone, body, name: chosen.known ? '' : chosen.name })
      await queryClient.invalidateQueries({ queryKey: messagingKeys.simulatorThread(chosen.phone) })
      await queryClient.invalidateQueries({ queryKey: messagingKeys.all })
    } catch (error) {
      toast.error(errorMessage(error, t))
      throw error
    } finally {
      setSending(false)
    }
  }

  const name = thread.data?.guest?.full_name || chosen?.name || chosen?.phone || ''

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-6">
      <PageHeader title={t('simulator.title')} description={t('simulator.description')} />
      {!enabled && (
        <div role="status" className="flex flex-col gap-3 rounded-xl border border-warning/30 bg-warning-soft p-4 sm:flex-row sm:items-center">
          <SmartphoneNfc aria-hidden className="size-5 shrink-0 text-warning-ink" />
          <div className="flex-1">
            <p className="font-semibold text-warning-ink">{t('simulator.disabledTitle')}</p>
            <p className="text-sm text-warning-ink">{t('simulator.disabledDescription')}</p>
          </div>
          <Button asChild variant="secondary" size="sm">
            <Link to="/app/settings/integrations">{t('simulator.openIntegrations')}</Link>
          </Button>
        </div>
      )}
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="grid gap-6">
          <section aria-labelledby="sim-contacts" className="grid gap-3 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5">
            <div>
              <h2 id="sim-contacts" className="font-bold">
                {t('simulator.contacts')}
              </h2>
              <p className="text-[13px] text-muted">{t('simulator.contactsHint')}</p>
            </div>
            <div className="relative">
              <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
              <Input
                type="search"
                name="contacts"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label={t('simulator.searchContacts')}
                placeholder={t('simulator.searchContacts')}
                className="pl-9"
              />
            </div>
            {contacts.isPending ? (
              <LoadingState variant="rows" rows={4} />
            ) : contacts.isError ? (
              <ErrorState error={contacts.error} onRetry={() => contacts.refetch()} />
            ) : contacts.data.results.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted">{t('simulator.noContacts')}</p>
            ) : (
              <ul className="grid max-h-[22rem] gap-1 overflow-y-auto">
                {contacts.data.results.map((contact) => (
                  <li key={contact.guest_id}>
                    <ContactButton
                      contact={contact}
                      selected={chosen?.phone === contact.phone}
                      onChoose={() => setChosen({ phone: contact.phone, name: contact.full_name, known: true })}
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>
          <OtherNumber disabled={!enabled} onUse={(phone, contactName) => setChosen({ phone, name: contactName, known: false })} />
        </div>

        <div className="lg:sticky lg:top-20">
          {chosen ? (
            <PhoneMockup
              key={chosen.phone}
              label={t('simulator.phoneLabel', { name })}
              hotelName={property?.name ?? ''}
              messages={thread.data?.messages ?? []}
              notice={thread.data && !thread.data.guest ? t('simulator.newContact') : undefined}
              disabled={!enabled}
              sending={sending}
              onSend={send}
              footer={
                thread.data?.conversation_id ? (
                  <Link
                    to={`/app/inbox?c=${thread.data.conversation_id}`}
                    className="inline-flex items-center gap-1 text-sm font-semibold text-accent-ink hover:underline"
                  >
                    {t('simulator.openInbox')}
                    <ArrowUpRight aria-hidden className="size-4" />
                  </Link>
                ) : undefined
              }
            />
          ) : (
            <div className="grid min-h-[24rem] place-items-center rounded-[2.2rem] border-2 border-dashed border-border-strong p-8 text-center text-sm text-muted">
              <span>
                <Phone aria-hidden className="mx-auto mb-3 size-6 text-subtle" />
                {t('simulator.choose')}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ContactButton({ contact, selected, onChoose }: { contact: SimulatorContact; selected: boolean; onChoose: () => void }) {
  const { t } = useTranslation('messaging')
  return (
    <button
      type="button"
      onClick={onChoose}
      aria-pressed={selected}
      className={cn(
        'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors hover:bg-surface-2',
        'focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:outline-none',
        selected && 'bg-accent-soft/60 hover:bg-accent-soft/70',
      )}
    >
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[14px] font-semibold">{contact.full_name}</span>
        <span className="num block text-[12px] text-muted">{contact.phone}</span>
      </span>
      {contact.reservation && (
        <span className="flex shrink-0 flex-col items-end gap-1">
          <span className="num text-[11px] text-muted">{t('simulator.reservation', { code: contact.reservation.code })}</span>
          <StatusBadge kind="reservation" status={contact.reservation.status} />
        </span>
      )}
    </button>
  )
}

function OtherNumber({ disabled, onUse }: { disabled: boolean; onUse: (phone: string, name: string) => void }) {
  const { t } = useTranslation('messaging')
  const ids = useId()
  const [phone, setPhone] = useState('')
  const [name, setName] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    const value = phone.trim()
    if (!value) return
    onUse(value, name.trim())
  }

  return (
    <form onSubmit={submit} className="grid gap-3 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5" noValidate>
      <h2 className="font-bold">{t('simulator.otherNumber')}</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label htmlFor={`${ids}-phone`}>{t('simulator.phone')}</Label>
          <Input
            id={`${ids}-phone`}
            name="phone"
            type="tel"
            inputMode="tel"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder={t('simulator.phonePlaceholder')}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={`${ids}-name`}>{t('simulator.name')}</Label>
          <Input
            id={`${ids}-name`}
            name="name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t('simulator.namePlaceholder')}
          />
        </div>
      </div>
      <div>
        <Button type="submit" disabled={disabled || !phone.trim()}>
          {t('simulator.use')}
        </Button>
      </div>
    </form>
  )
}
