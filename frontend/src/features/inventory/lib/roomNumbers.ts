/**
 * Room numbers for bulk creation: `"101-110,201,203"` → `["101", …, "110", "201", "203"]`.
 * Same rules as the backend (apps/inventory/numbering.py), so the preview shows exactly what the API
 * creates: a part is a range when both ends are `<letters><digits>` with the same letters ("A8-A10",
 * "B1-3", "01-03" keeps the padding); anything else is a literal label ("Suite Mar", "PH-1").
 */

export const MAX_ROOMS_PER_REQUEST = 500
export const MAX_NUMBER_LENGTH = 20

export type RoomNumbersErrorCode = 'empty' | 'reversed' | 'prefix' | 'tooLong' | 'tooMany'

export interface RoomNumbersError {
  code: RoomNumbersErrorCode
  part?: string
}

export interface ParsedRoomNumbers {
  numbers: string[]
  error: RoomNumbersError | null
}

const SEPARATORS = /[,;\n]/
const RANGE = /^([A-Za-z]*)(\d+)\s*-\s*([A-Za-z]*)(\d+)$/
const FLOOR = /^[A-Za-z]*(\d{3,})$/

class ParseError extends Error {
  constructor(public detail: RoomNumbersError) {
    super(detail.code)
  }
}

function expand(part: string): string[] {
  const match = RANGE.exec(part)
  if (!match) {
    if (part.length > MAX_NUMBER_LENGTH) throw new ParseError({ code: 'tooLong', part })
    return [part]
  }
  const [, prefix = '', first = '', endPrefix = '', last = ''] = match
  if (endPrefix && endPrefix !== prefix) throw new ParseError({ code: 'prefix', part })
  const start = Number(first)
  const end = Number(last)
  if (end < start) throw new ParseError({ code: 'reversed', part })
  if (end - start + 1 > MAX_ROOMS_PER_REQUEST) throw new ParseError({ code: 'tooMany', part })
  const numbers: string[] = []
  for (let value = start; value <= end; value++) numbers.push(`${prefix}${String(value).padStart(first.length, '0')}`)
  const tooLong = numbers.find((number) => number.length > MAX_NUMBER_LENGTH)
  if (tooLong) throw new ParseError({ code: 'tooLong', part: tooLong })
  return numbers
}

export function parseRoomNumbers(spec: string): ParsedRoomNumbers {
  try {
    const numbers: string[] = []
    for (const raw of spec.split(SEPARATORS)) {
      const part = raw.trim()
      if (!part) continue
      numbers.push(...expand(part))
      if (numbers.length > MAX_ROOMS_PER_REQUEST) throw new ParseError({ code: 'tooMany' })
    }
    if (numbers.length === 0) throw new ParseError({ code: 'empty' })
    return { numbers, error: null }
  } catch (error) {
    if (error instanceof ParseError) return { numbers: [], error: error.detail }
    throw error
  }
}

/** Numbers that appear more than once, each listed once, in order of first repetition. */
export function duplicatesIn(numbers: string[]): string[] {
  const seen = new Set<string>()
  const repeated: string[] = []
  for (const number of numbers) {
    if (seen.has(number) && !repeated.includes(number)) repeated.push(number)
    seen.add(number)
  }
  return repeated
}

/** Hotel convention: the digits before the last two are the floor ("101" → "1"); otherwise "". */
export function inferFloor(number: string): string {
  const match = FLOOR.exec(number.trim())
  if (!match?.[1]) return ''
  return String(Number(match[1].slice(0, -2)))
}
