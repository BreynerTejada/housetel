import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { MoneyInput, MoneyText } from '@/components/Money'

function Harness({ initial = '', currency }: { initial?: string; currency?: string }) {
  const [value, setValue] = useState(initial)
  return (
    <>
      <label htmlFor="price">Precio</label>
      <MoneyInput id="price" value={value} onChange={setValue} currency={currency} />
      <output data-testid="raw">{JSON.stringify(value)}</output>
    </>
  )
}

const raw = () => JSON.parse(screen.getByTestId('raw').textContent ?? '""')

describe('MoneyInput', () => {
  it('shows API amounts with Colombian thousands separators', () => {
    render(<Harness initial="350000.00" />)
    expect(screen.getByLabelText('Precio')).toHaveValue('350.000')
  })

  it('formats while typing and reports plain digits', async () => {
    render(<Harness />)
    await userEvent.type(screen.getByLabelText('Precio'), '1234567')
    expect(screen.getByLabelText('Precio')).toHaveValue('1.234.567')
    expect(raw()).toBe('1234567')
  })

  it('ignores letters and symbols, including a pasted formatted amount', async () => {
    render(<Harness />)
    const input = screen.getByLabelText('Precio')
    await userEvent.click(input)
    await userEvent.paste('$ 320.000 COP')
    expect(input).toHaveValue('320.000')
    expect(raw()).toBe('320000')
  })

  it('reports an empty string when cleared', async () => {
    render(<Harness initial="90000" />)
    await userEvent.clear(screen.getByLabelText('Precio'))
    expect(raw()).toBe('')
  })

  it('keeps two decimals for other currencies', async () => {
    render(<Harness currency="USD" />)
    await userEvent.type(screen.getByLabelText('Precio'), '1234,5')
    expect(screen.getByLabelText('Precio')).toHaveValue('1.234,5')
    expect(raw()).toBe('1234.5')
  })
})

describe('MoneyText', () => {
  it('renders COP amounts with tabular figures', () => {
    render(<MoneyText value="320000.00" />)
    const text = screen.getByText(/320\.000/)
    expect(text.textContent?.replace(/\s/g, ' ')).toBe('$ 320.000')
    expect(text).toHaveClass('num')
  })
})
