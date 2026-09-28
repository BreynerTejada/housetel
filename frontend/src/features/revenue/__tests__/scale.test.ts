import { describe, expect, it } from 'vitest'
import { stepOf } from '../lib/scale'

describe('stepOf', () => {
  it.each([
    ['0', 0],
    ['0.5', 1],
    ['5.99', 1],
    ['6.00', 2], // a boundary belongs to the stronger step
    ['11.99', 2],
    ['12.00', 3],
    ['40', 3],
    ['-0.5', -1],
    ['-6', -2],
    ['-12.00', -3],
    ['-25', -3],
  ])('%s %% of change is step %i of the diverging scale', (change, step) => {
    expect(stepOf(change)).toBe(step)
  })

  it('reads anything that is not a number as no change', () => {
    expect(stepOf('abc')).toBe(0)
  })
})
