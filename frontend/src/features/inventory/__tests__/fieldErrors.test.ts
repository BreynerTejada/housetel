import { describe, expect, it } from 'vitest'
import { flattenFieldErrors } from '../lib/fieldErrors'

describe('flattenFieldErrors', () => {
  it('turns the API `fields` into one message per dotted key', () => {
    expect(
      flattenFieldErrors({
        number: ['Ya existe una habitación con este número'],
        custom_values: { minibar: ['Este campo es obligatorio'] },
        overrides: { max_adults: ['No puede superar la ocupación máxima (3)'] },
      }),
    ).toEqual({
      number: 'Ya existe una habitación con este número',
      'custom_values.minibar': 'Este campo es obligatorio',
      'overrides.max_adults': 'No puede superar la ocupación máxima (3)',
    })
  })

  it('joins several messages of one field and numbers list items', () => {
    expect(flattenFieldErrors({ name: ['Muy largo', 'Inválido'], beds: [{ count: ['Entre 1 y 20'] }] })).toEqual({
      name: 'Muy largo Inválido',
      'beds.0.count': 'Entre 1 y 20',
    })
  })

  it('ignores a missing or malformed value', () => {
    expect(flattenFieldErrors(undefined)).toEqual({})
    expect(flattenFieldErrors('texto')).toEqual({})
  })
})
