import { screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { DatePicker, DateRangePicker } from '@/components/DatePicker'
import type { DateRangeValue } from '@/lib/date-ranges'
import { renderWithProviders } from '@/test/render'

function SingleHarness() {
  const [value, setValue] = useState<string | null>('2026-10-12')
  return (
    <>
      <DatePicker value={value} onChange={setValue} aria-label="Llegada" />
      <output data-testid="value">{String(value)}</output>
    </>
  )
}

function RangeHarness({ minNights }: { minNights?: number }) {
  const [value, setValue] = useState<DateRangeValue | null>(null)
  return (
    <>
      <DateRangePicker
        value={value}
        onChange={setValue}
        today="2026-10-01"
        showNights
        minNights={minNights}
        presets={['today', 'last30']}
        aria-label="Fechas de la estadía"
      />
      <output data-testid="value">{JSON.stringify(value)}</output>
    </>
  )
}

const value = () => screen.getByTestId('value').textContent

describe('DatePicker', () => {
  it('shows the date and emits the picked day as YYYY-MM-DD', async () => {
    const { user } = renderWithProviders(<SingleHarness />)
    const trigger = screen.getByRole('button', { name: /Llegada/ })
    expect(trigger).toHaveTextContent('lun 12 oct 2026')

    await user.click(trigger)
    await user.click(screen.getByRole('button', { name: /15 de octubre de 2026/ }))

    expect(value()).toBe('2026-10-15')
    expect(screen.getByRole('button', { name: /Llegada/ })).toHaveTextContent('jue 15 oct 2026')
  })
})

describe('DateRangePicker', () => {
  it('waits for the second day and then emits the ordered range with the nights', async () => {
    const { user } = renderWithProviders(<RangeHarness />)
    const trigger = screen.getByRole('button', { name: /Fechas de la estadía/ })
    expect(trigger).toHaveTextContent('Elegir fechas')

    await user.click(trigger)
    await user.click(screen.getByRole('button', { name: /15 de octubre de 2026/ }))
    expect(value()).toBe('null')

    await user.click(screen.getByRole('button', { name: /12 de octubre de 2026/ }))

    expect(value()).toBe('{"from":"2026-10-12","to":"2026-10-15"}')
    expect(screen.getByRole('button', { name: /Fechas de la estadía/ })).toHaveTextContent('12–15 oct 2026')
    expect(screen.getByRole('button', { name: /Fechas de la estadía/ })).toHaveTextContent('3 noches')
  })

  it('offers presets relative to the business date', async () => {
    const { user } = renderWithProviders(<RangeHarness />)
    await user.click(screen.getByRole('button', { name: /Fechas de la estadía/ }))

    await user.click(screen.getByRole('button', { name: 'Últimos 30 días' }))

    expect(value()).toBe('{"from":"2026-09-02","to":"2026-10-01"}')
  })

  it('does not accept a zero-night stay when a minimum is set', async () => {
    const { user } = renderWithProviders(<RangeHarness minNights={1} />)
    await user.click(screen.getByRole('button', { name: /Fechas de la estadía/ }))

    await user.click(screen.getByRole('button', { name: /12 de octubre de 2026/ }))
    await user.click(screen.getByRole('button', { name: /12 de octubre de 2026/ }))
    expect(value()).toBe('null')

    await user.click(screen.getByRole('button', { name: /13 de octubre de 2026/ }))
    expect(value()).toBe('{"from":"2026-10-12","to":"2026-10-13"}')
  })
})
