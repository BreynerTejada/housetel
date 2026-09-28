import { useQuery } from '@tanstack/react-query'
import { ImageOff } from 'lucide-react'
import { useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { fetchPhoto, type TicketPhoto } from '../api'

/**
 * A damage photo. Photos are private (they can show guests' belongings): they are downloaded with the session
 * and `X-Property-Id` and shown through an object URL, never linked under /media/.
 */
export function PrivatePhoto({ photo, alt, className }: { photo: TicketPhoto; alt: string; className?: string }) {
  const { t } = useTranslation('housekeeping')
  const query = useQuery({
    queryKey: ['housekeeping', 'photo', photo.id],
    queryFn: ({ signal }) => fetchPhoto(photo.file_url, signal),
    staleTime: 5 * 60_000,
  })
  const url = useMemo(() => (query.data ? URL.createObjectURL(query.data) : null), [query.data])
  useEffect(() => () => (url ? URL.revokeObjectURL(url) : undefined), [url])

  if (query.isPending) return <Skeleton className={cn('aspect-[4/3] w-full rounded-lg', className)} />
  if (!url)
    return (
      <span
        role="img"
        aria-label={t('ticket.photoError')}
        className={cn('grid aspect-[4/3] w-full place-items-center rounded-lg bg-surface-2 text-muted', className)}
      >
        <ImageOff aria-hidden className="size-5" />
      </span>
    )
  return (
    <a href={url} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55">
      <img src={url} alt={alt} className={cn('aspect-[4/3] w-full object-cover', className)} />
    </a>
  )
}
