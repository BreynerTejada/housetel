import { CalendarSync } from 'lucide-react'
import type { ChannelCode } from '../api'
import { cn } from '@/lib/utils'

const MARKS: Record<ChannelCode, { text: string; tone: string }> = {
  booksim: { text: 'BS', tone: 'bg-info-soft text-info-ink' },
  airsim: { text: 'AS', tone: 'bg-danger-soft text-danger-ink' },
  channex: { text: 'CX', tone: 'bg-success-soft text-success-ink' },
  ical: { text: '', tone: 'bg-stone-soft text-stone-ink' },
}

/** The channel's badge: its initials (BookSim, AirSim, Channex) or a calendar (iCal). */
export function ChannelMark({ channel, size = 'md', className }: { channel: ChannelCode; size?: 'sm' | 'md' | 'lg'; className?: string }) {
  const mark = MARKS[channel]
  const dimensions = size === 'sm' ? 'size-6 text-[10px] rounded-md' : size === 'lg' ? 'size-12 text-base rounded-xl' : 'size-9 text-xs rounded-lg'
  return (
    <span aria-hidden className={cn('grid shrink-0 place-items-center font-extrabold tracking-wide', dimensions, mark.tone, className)}>
      {mark.text || <CalendarSync className={size === 'sm' ? 'size-3.5' : size === 'lg' ? 'size-6' : 'size-4'} />}
    </span>
  )
}
