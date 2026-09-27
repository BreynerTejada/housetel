import { Download, EllipsisVertical, Eraser, Pencil, Trash2, Users } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { useGuestTabs } from '@/app/extensions'
import { ConfirmDialog, DangerConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import {
  downloadGuestExport,
  useAnonymizeGuest,
  useDeleteGuest,
  useGuest,
  useGuestDuplicates,
  type DuplicateGuest,
  type Guest,
} from '../api'
import { DocumentsPanel } from '../components/DocumentsPanel'
import { GuestFormDialog } from '../components/GuestFormDialog'
import { MergeGuestsDialog } from '../components/MergeGuestsDialog'
import { NotesPanel } from '../components/NotesPanel'
import { RegistrationCard } from '../components/RegistrationCard'
import { StaysPanel } from '../components/StaysPanel'
import { SummaryPanel } from '../components/SummaryPanel'

export default function GuestDetailPage() {
  const { id = '' } = useParams()
  const { t } = useTranslation('guests')
  const guest = useGuest(id)
  const inactive = Boolean(guest.data?.merged_into || guest.data?.anonymized_at)
  const duplicates = useGuestDuplicates(id, Boolean(guest.data) && !inactive)

  if (guest.isPending) return <LoadingState />
  if (guest.isError) return <ErrorState error={guest.error} onRetry={() => void guest.refetch()} />
  return (
    // grid-cols-1 = minmax(0, 1fr): the column never grows to the widest child (the tab row), so phones keep
    // the page gutter and the tabs scroll inside it.
    <div className="mx-auto grid w-full max-w-7xl grid-cols-1 gap-5">
      <nav aria-label={t('detail.breadcrumb')} className="text-[13px] text-muted">
        <Link to="/app/guests" className="rounded-sm hover:text-fg hover:underline">
          {t('nav.guests')}
        </Link>
      </nav>
      {/* keyed by guest: dialogs and tab state start fresh when navigating to another profile */}
      <GuestProfile key={guest.data.id} guest={guest.data} duplicates={inactive ? [] : (duplicates.data ?? [])} />
    </div>
  )
}

function GuestProfile({ guest, duplicates }: { guest: Guest; duplicates: DuplicateGuest[] }) {
  const { t, i18n } = useTranslation('guests')
  const lang = normalizeLang(i18n.language)
  const navigate = useNavigate()
  const extensionTabs = useGuestTabs()
  const canManage = useCan('guests.manage')
  const canMerge = useCan('guests.merge')
  const canExport = useCan('guests.export')
  const anonymize = useAnonymizeGuest(guest.id)
  const remove = useDeleteGuest()
  const [editing, setEditing] = useState(false)
  const [merging, setMerging] = useState(false)
  const [erasing, setErasing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const readOnly = Boolean(guest.merged_into || guest.anonymized_at)

  async function exportData() {
    try {
      await downloadGuestExport(guest)
      toast.success(t('export.done'))
    } catch (error) {
      toast.error(errorMessage(error, t))
    }
  }

  const actions = !readOnly && (canManage || canExport) && (
    <>
      {canManage && (
        <Button onClick={() => setEditing(true)}>
          <Pencil aria-hidden />
          {t('detail.edit')}
        </Button>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="secondary" size="icon" aria-label={t('detail.actions')}>
            <EllipsisVertical aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {canExport && (
            <DropdownMenuItem onSelect={() => void exportData()}>
              <Download aria-hidden />
              {t('detail.export')}
            </DropdownMenuItem>
          )}
          {canExport && (
            <DropdownMenuItem destructive onSelect={() => setErasing(true)}>
              <Eraser aria-hidden />
              {t('detail.anonymize')}
            </DropdownMenuItem>
          )}
          {canManage && (
            <>
              {canExport && <DropdownMenuSeparator />}
              <DropdownMenuItem destructive onSelect={() => setDeleting(true)}>
                <Trash2 aria-hidden />
                {t('detail.delete')}
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  )

  return (
    <>
      <RegistrationCard guest={guest} actions={actions} />

      {guest.merged_into && (
        <Banner tone="info">
          <span>{t('detail.mergedBanner')}</span>
          <Link to={`/app/guests/${guest.merged_into}`} className="font-semibold text-info-ink underline underline-offset-4">
            {t('detail.openPrimary')}
          </Link>
        </Banner>
      )}
      {guest.anonymized_at && (
        <Banner tone="stone">{t('detail.anonymizedBanner', { date: formatDate(guest.anonymized_at, undefined, lang) })}</Banner>
      )}
      {duplicates.length > 0 && (
        <Banner tone="warning">
          <span className="flex items-center gap-2">
            <Users aria-hidden className="size-4 shrink-0" />
            {t('duplicates.banner', { count: duplicates.length })}
          </span>
          {canMerge ? (
            <Button size="sm" onClick={() => setMerging(true)}>
              {t('duplicates.review')}
            </Button>
          ) : (
            <span className="text-xs">{t('duplicates.askManager')}</span>
          )}
        </Banner>
      )}

      <Tabs defaultValue="summary">
        <TabsList>
          <TabsTrigger value="summary">{t('detail.tabs.summary')}</TabsTrigger>
          <TabsTrigger value="stays">
            {t('detail.tabs.stays')}
            <Count value={guest.stats.reservations_count} />
          </TabsTrigger>
          <TabsTrigger value="documents">
            {t('detail.tabs.documents')}
            <Count value={guest.documents_count} />
          </TabsTrigger>
          <TabsTrigger value="notes">{t('detail.tabs.notes')}</TabsTrigger>
          {extensionTabs.map((tab) => (
            <TabsTrigger key={tab.id} value={`ext-${tab.id}`}>
              {t(tab.labelKey)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="summary">
          <SummaryPanel guest={guest} readOnly={readOnly} />
        </TabsContent>
        <TabsContent value="stays">
          <StaysPanel guestId={guest.id} />
        </TabsContent>
        <TabsContent value="documents">
          <DocumentsPanel guestId={guest.id} readOnly={readOnly} />
        </TabsContent>
        <TabsContent value="notes">
          <NotesPanel guest={guest} readOnly={readOnly} />
        </TabsContent>
        {extensionTabs.map((tab) => (
          <TabsContent key={tab.id} value={`ext-${tab.id}`}>
            <tab.Component guestId={guest.id} />
          </TabsContent>
        ))}
      </Tabs>

      <GuestFormDialog open={editing} onOpenChange={setEditing} guest={guest} />
      {duplicates.length > 0 && merging && (
        <MergeGuestsDialog
          guest={guest}
          candidates={duplicates}
          open={merging}
          onOpenChange={setMerging}
          onMerged={(primary) => primary.id !== guest.id && navigate(`/app/guests/${primary.id}`)}
        />
      )}
      <DangerConfirmDialog
        open={erasing}
        onOpenChange={setErasing}
        title={t('anonymize.title', { name: guest.full_name })}
        description={t('anonymize.description')}
        confirmText={t('anonymize.confirmText')}
        confirmLabel={t('anonymize.confirm')}
        onConfirm={async () => {
          await anonymize.mutateAsync()
          toast.success(t('anonymize.done'))
        }}
      />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={t('delete.title')}
        description={t('delete.description')}
        confirmLabel={t('delete.confirm')}
        onConfirm={async () => {
          await remove.mutateAsync(guest.id)
          toast.success(t('delete.done'))
          navigate('/app/guests')
        }}
      />
    </>
  )
}

const BANNER_TONES = {
  info: 'border-info/25 bg-info-soft text-info-ink',
  warning: 'border-warning/30 bg-warning-soft text-warning-ink',
  stone: 'border-stone/25 bg-stone-soft text-stone-ink',
}

function Banner({ tone, children }: { tone: keyof typeof BANNER_TONES; children: ReactNode }) {
  return (
    <div className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm font-medium ${BANNER_TONES[tone]}`}>
      {children}
    </div>
  )
}

function Count({ value }: { value: number }) {
  if (!value) return null
  return <span className="num rounded-full bg-surface-2 px-1.5 text-[11px] leading-4 text-muted">{value}</span>
}
