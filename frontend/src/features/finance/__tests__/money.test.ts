import { describe, expect, it } from 'vitest'
import { balanceState, cashVerdict, countDenominations, plainAmount, toCents } from '../money'

describe('plainAmount', () => {
  it('writes the amount the way people type it to confirm (COP, no symbol)', () => {
    expect(plainAmount('83300.00')).toBe('83.300')
    expect(plainAmount('1500000')).toBe('1.500.000')
    expect(plainAmount('-30000.00')).toBe('-30.000')
  })
})

describe('balanceState', () => {
  it('tells owed, settled and credit apart', () => {
    expect(balanceState('441650.00')).toBe('due')
    expect(balanceState('0.00')).toBe('settled')
    expect(balanceState('-10000.00')).toBe('credit')
    expect(balanceState(null)).toBe('settled')
  })
})

describe('countDenominations', () => {
  it('adds bills and coins', () => {
    expect(countDenominations({ '100000': 2, '50000': 1, '500': 3 })).toBe(251500)
    expect(countDenominations({})).toBe(0)
  })
})

describe('cashVerdict', () => {
  it('compares the count with what the drawer should have', () => {
    expect(cashVerdict(300000, '300000.00')).toEqual({ kind: 'exact', amount: 0 })
    expect(cashVerdict(305000, '300000.00')).toEqual({ kind: 'over', amount: 5000 })
    expect(cashVerdict(250000, '300000.00')).toEqual({ kind: 'short', amount: 50000 })
  })
})

describe('toCents', () => {
  it('avoids floating point drift when adding money strings', () => {
    expect(toCents('0.10') + toCents('0.20')).toBe(30)
    expect(toCents('433300.00')).toBe(43330000)
  })
})
