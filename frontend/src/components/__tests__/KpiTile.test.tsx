import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { KpiTile } from '@/components/KpiTile'

const week = [
  { label: 'lun 5 oct', value: 62 },
  { label: 'mar 6 oct', value: 70 },
  { label: 'mié 7 oct', value: 81 },
]

describe('KpiTile', () => {
  it('shows the label, the value and the named comparison period', () => {
    render(<KpiTile label="Ocupación" value="81%" delta={4.2} deltaLabel="4,2 pp" deltaPeriod="vs. semana pasada" />)
    expect(screen.getByText('Ocupación')).toBeInTheDocument()
    expect(screen.getByText('81%')).toBeInTheDocument()
    expect(screen.getByText('vs. semana pasada')).toBeInTheDocument()
  })

  it('marks a rise as good when higher is better, with words and not only color', () => {
    render(<KpiTile label="Ocupación" value="81%" delta={4.2} deltaLabel="4,2 pp" />)
    const delta = screen.getByText('Sube 4,2 pp').closest('[data-intent]')
    expect(delta).toHaveAttribute('data-intent', 'good')
    expect(delta).toHaveAttribute('data-direction', 'up')
  })

  it('marks a rise as bad when lower is better (e.g. cancellations)', () => {
    render(<KpiTile label="Cancelaciones" value="12" delta={3} deltaLabel="3" intent="lower-is-better" />)
    expect(screen.getByText('Sube 3').closest('[data-intent]')).toHaveAttribute('data-intent', 'bad')
  })

  it('reports no change as neutral', () => {
    render(<KpiTile label="ADR" value="$ 320.000" delta={0} />)
    expect(screen.getByText('Sin cambio').closest('[data-intent]')).toHaveAttribute('data-intent', 'neutral')
  })

  it('formats the delta when no label is given', () => {
    render(<KpiTile label="Llegadas" value="18" delta={-2.5} />)
    expect(screen.getByText('Baja 2,5').closest('[data-intent]')).toHaveAttribute('data-intent', 'bad')
  })

  it('offers the trend as a table for screen readers', () => {
    render(<KpiTile label="Ocupación" value="81%" trend={week} formatTrendValue={(v) => `${v}%`} />)
    const table = screen.getByRole('table', { name: 'Ocupación' })
    expect(within(table).getAllByRole('row')).toHaveLength(4)
    expect(within(table).getByText('mié 7 oct')).toBeInTheDocument()
    expect(within(table).getByText('81%')).toBeInTheDocument()
  })

  it('reads out a point of the trend while moving through it with the keyboard', () => {
    render(<KpiTile label="Ocupación" value="81%" trend={week} formatTrendValue={(v) => `${v}%`} />)
    const chart = screen.getByRole('img', { name: /Ocupación/ })

    fireEvent.focus(chart)
    expect(screen.getByRole('status')).toHaveTextContent('mié 7 oct · 81%')

    fireEvent.keyDown(chart, { key: 'ArrowLeft' })
    expect(screen.getByRole('status')).toHaveTextContent('mar 6 oct · 70%')

    fireEvent.keyDown(chart, { key: 'Home' })
    expect(screen.getByRole('status')).toHaveTextContent('lun 5 oct · 62%')
  })
})
