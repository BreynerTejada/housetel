import { describe, expect, it } from 'vitest'
import { duplicatesIn, inferFloor, parseRoomNumbers } from '../lib/roomNumbers'

// Mirrors backend apps/inventory/numbering.py so the bulk-create preview matches what the API creates.
describe('parseRoomNumbers', () => {
  it('expands ranges and keeps single numbers in order', () => {
    expect(parseRoomNumbers('101-103,105')).toEqual({ numbers: ['101', '102', '103', '105'], error: null })
  })

  it('accepts spaces, semicolons and new lines', () => {
    expect(parseRoomNumbers(' 201 - 202 ;\n301,  302 ').numbers).toEqual(['201', '202', '301', '302'])
  })

  it('keeps zero padding and letter prefixes, and labels that are not ranges', () => {
    expect(parseRoomNumbers('01-03').numbers).toEqual(['01', '02', '03'])
    expect(parseRoomNumbers('A8-A10').numbers).toEqual(['A8', 'A9', 'A10'])
    expect(parseRoomNumbers('Suite Mar,PH-1').numbers).toEqual(['Suite Mar', 'PH-1'])
  })

  it.each([
    ['', 'empty'],
    ['110-101', 'reversed'],
    ['A1-B3', 'prefix'],
    ['12345678901234567890X', 'tooLong'],
    ['1-501', 'tooMany'],
  ])('reports %j as %s', (spec, error) => {
    expect(parseRoomNumbers(spec)).toMatchObject({ numbers: [], error: { code: error } })
  })

  it('names the part that is wrong', () => {
    expect(parseRoomNumbers('101-103,120-110').error).toEqual({ code: 'reversed', part: '120-110' })
  })
})

describe('duplicatesIn', () => {
  it('lists each repeated number once, in order', () => {
    expect(duplicatesIn(['101', '102', '101', '103', '102', '101'])).toEqual(['101', '102'])
  })
})

describe('inferFloor', () => {
  it.each([
    ['101', '1'],
    ['1203', '12'],
    ['A204', '2'],
    ['12', ''],
    ['D1', ''],
  ])('%s → %j', (number, floor) => {
    expect(inferFloor(number)).toBe(floor)
  })
})
