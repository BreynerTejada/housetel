import { describe, expect, it } from 'vitest'
import { ApiError } from '@/lib/api'
import { fieldErrors, firstMessage, i18nValue, parseDecimal, toI18n } from '../lib/forms'

describe('server validation errors', () => {
  it('reads the first message of nested DRF errors', () => {
    expect(firstMessage(['Ya existe', 'otra'])).toBe('Ya existe')
    expect(firstMessage({ 1: ['Este campo no puede estar en blanco.'] })).toBe('Este campo no puede estar en blanco.')
    expect(firstMessage(undefined)).toBe('')
  })

  it('maps API fields onto form fields and keeps the rest as a general message', () => {
    const error = new ApiError(400, 'validation_error', 'Ya existe un registro con este código', {
      code: ['Ya existe un registro con este código'],
      name: ['El texto en español es obligatorio'],
      detail_only: ['x'],
    })
    expect(fieldErrors(error, { code: 'code', name: 'name_es' })).toEqual({
      fields: { code: 'Ya existe un registro con este código', name_es: 'El texto en español es obligatorio' },
      general: 'Ya existe un registro con este código',
    })
  })

  it('has no general message when every field is shown next to its input', () => {
    const error = new ApiError(400, 'validation_error', 'Mal', { rate: ['Mal'] })
    expect(fieldErrors(error, { rate: 'rate' })).toEqual({ fields: { rate: 'Mal' }, general: null })
  })

  it('shows domain errors without fields and non-API errors as general messages', () => {
    const conflict = new ApiError(409, 'in_use', 'Está en uso: desactívalo en lugar de eliminarlo')
    expect(fieldErrors(conflict, {})).toEqual({ fields: {}, general: 'Está en uso: desactívalo en lugar de eliminarlo' })
    expect(fieldErrors(new Error('boom'), {})).toEqual({ fields: {}, general: null })
  })
})

describe('translatable texts', () => {
  it('builds and reads {es, en}', () => {
    expect(toI18n(' Desayuno ', '')).toEqual({ es: 'Desayuno', en: '' })
    expect(i18nValue({ es: 'Desayuno', en: 'Breakfast' })).toEqual({ es: 'Desayuno', en: 'Breakfast' })
    expect(i18nValue(undefined)).toEqual({ es: '', en: '' })
  })
})

describe('decimals typed with comma or dot', () => {
  it.each([
    ['19', '19'],
    ['1,5', '1.5'],
    [' 12.25 ', '12.25'],
    ['-12', '-12'],
  ])('reads %j as %s', (typed, value) => {
    expect(parseDecimal(typed)).toBe(value)
  })

  it.each(['', 'abc', '1,2,3', '1.234'])('rejects %j', (typed) => {
    expect(parseDecimal(typed)).toBeNull()
  })

  it('can forbid negative numbers', () => {
    expect(parseDecimal('-5', { signed: false })).toBeNull()
  })
})
