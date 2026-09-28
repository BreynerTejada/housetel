/** "Add to calendar": an iCalendar (RFC 5545) all-day event from check-in to the (exclusive) check-out day. */

export interface IcsBooking {
  code: string
  hotelName: string
  address: string
  /** `YYYY-MM-DD` */
  checkin: string
  /** `YYYY-MM-DD` (exclusive, which is exactly what DTEND means for all-day events) */
  checkout: string
  description: string
  url: string
  now?: Date
}

const MAX_OCTETS = 75
const encoder = new TextEncoder()

/** TEXT values escape backslashes, semicolons, commas and line breaks. */
function escapeText(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n')
}

/** Content lines longer than 75 octets continue on lines that start with a space (never inside a character). */
function fold(line: string): string[] {
  const lines: string[] = []
  let current = ''
  let octets = 0
  for (const char of line) {
    const size = encoder.encode(char).length
    if (octets + size > MAX_OCTETS) {
      lines.push(current)
      current = ' '
      octets = 1
    }
    current += char
    octets += size
  }
  lines.push(current)
  return lines
}

const compactDate = (iso: string) => iso.replace(/-/g, '')
const stamp = (date: Date) => date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '')

export function buildIcs({ code, hotelName, address, checkin, checkout, description, url, now = new Date() }: IcsBooking): string {
  const details = [description, url].filter(Boolean).join('\n')
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Housetel//Reservas//ES',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    'BEGIN:VEVENT',
    `UID:${code}@housetel.co`,
    `DTSTAMP:${stamp(now)}`,
    `DTSTART;VALUE=DATE:${compactDate(checkin)}`,
    `DTEND;VALUE=DATE:${compactDate(checkout)}`,
    `SUMMARY:${escapeText(`${hotelName} · ${code}`)}`,
    ...(address ? [`LOCATION:${escapeText(address)}`] : []),
    ...(details ? [`DESCRIPTION:${escapeText(details)}`] : []),
    ...(url ? [`URL:${url}`] : []),
    'END:VEVENT',
    'END:VCALENDAR',
  ]
  return `${lines.flatMap(fold).join('\r\n')}\r\n`
}

/** Saves the event as `<code>.ics` (the browser offers to open it with the calendar app). */
export function downloadIcs(filename: string, content: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/calendar;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
