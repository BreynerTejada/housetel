import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/render'
import type { CustomFieldDefinition } from '../api'
import { CustomFieldInput } from '../components/CustomFieldInput'
import { orientationField } from './fixtures'

/** Options created through the API may carry numbers as values (the backend accepts text or numbers). */
const floorsField: CustomFieldDefinition = {
  ...orientationField,
  id: 'cf-floors',
  key: 'floor_level',
  label: { es: 'Nivel', en: 'Level' },
  options: [
    { value: 1, label: { es: 'Uno' } },
    { value: 2, label: { es: 'Dos' } },
  ],
}

describe('CustomFieldInput with numeric option values', () => {
  it('selects the option with its original value, not its text', async () => {
    const onChange = vi.fn()
    const { user } = renderWithProviders(<CustomFieldInput definition={floorsField} value={1} onChange={onChange} labelledBy="x" />)

    expect(screen.getByRole('combobox')).toHaveTextContent('Uno')
    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: 'Dos' }))

    expect(onChange).toHaveBeenCalledWith(2)
  })

  it('shows stored numeric values of a multiselect as checked and keeps their type', async () => {
    const onChange = vi.fn()
    const multi: CustomFieldDefinition = { ...floorsField, field_type: 'multiselect' }
    const { user } = renderWithProviders(<CustomFieldInput definition={multi} value={[1]} onChange={onChange} labelledBy="x" />)

    expect(screen.getByRole('checkbox', { name: 'Uno' })).toBeChecked()
    await user.click(screen.getByRole('checkbox', { name: 'Dos' }))

    expect(onChange).toHaveBeenCalledWith([1, 2])
  })
})
