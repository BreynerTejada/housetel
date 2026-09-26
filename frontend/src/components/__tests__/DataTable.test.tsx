import type { ColumnDef, PaginationState } from '@tanstack/react-table'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { DataTable } from '@/components/DataTable'

interface Row {
  id: string
  code: string
  guest: string
  nights: number
}

const columns: ColumnDef<Row>[] = [
  { accessorKey: 'code', header: 'Código' },
  { accessorKey: 'guest', header: 'Huésped' },
  { accessorKey: 'nights', header: 'Noches' },
]

const rows: Row[] = [
  { id: 'r1', code: 'HT-AAA111', guest: 'Camila Torres', nights: 3 },
  { id: 'r2', code: 'HT-BBB222', guest: 'John Smith', nights: 1 },
  { id: 'r3', code: 'HT-CCC333', guest: 'Andrés Gómez', nights: 5 },
]

const bodyRows = () => within(screen.getAllByRole('rowgroup')[1]!).getAllByRole('row')
const firstCells = () => bodyRows().map((row) => within(row).getAllByRole('cell')[0]?.textContent)

describe('DataTable (client data)', () => {
  it('renders one row per item', () => {
    render(<DataTable columns={columns} data={rows} getRowId={(r) => r.id} />)
    expect(bodyRows()).toHaveLength(3)
    expect(screen.getByText('Camila Torres')).toBeInTheDocument()
  })

  it('sorts when a column header is clicked', async () => {
    render(<DataTable columns={columns} data={rows} getRowId={(r) => r.id} />)

    await userEvent.click(screen.getByRole('button', { name: /Noches/ }))
    expect(firstCells()).toEqual(['HT-BBB222', 'HT-AAA111', 'HT-CCC333'])

    await userEvent.click(screen.getByRole('button', { name: /Noches/ }))
    expect(firstCells()).toEqual(['HT-CCC333', 'HT-AAA111', 'HT-BBB222'])
  })

  it('filters rows with the search box', async () => {
    render(<DataTable columns={columns} data={rows} getRowId={(r) => r.id} enableSearch />)
    await userEvent.type(screen.getByRole('searchbox'), 'smith')
    expect(firstCells()).toEqual(['HT-BBB222'])
  })

  it('paginates', async () => {
    const many = Array.from({ length: 12 }, (_, i) => ({ id: `r${i}`, code: `HT-${String(i).padStart(6, '0')}`, guest: `G${i}`, nights: i }))
    render(<DataTable columns={columns} data={many} getRowId={(r) => r.id} pageSize={10} />)

    expect(bodyRows()).toHaveLength(10)
    expect(screen.getByText('Página 1 de 2')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Página siguiente' }))
    expect(bodyRows()).toHaveLength(2)
    expect(screen.getByText('Página 2 de 2')).toBeInTheDocument()
  })

  it('reports the selected rows', async () => {
    const onSelectionChange = vi.fn()
    render(<DataTable columns={columns} data={rows} getRowId={(r) => r.id} enableSelection onSelectionChange={onSelectionChange} />)

    await userEvent.click(within(bodyRows()[2]!).getByRole('checkbox'))
    expect(onSelectionChange).toHaveBeenLastCalledWith([rows[2]])

    await userEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar todas las filas' }))
    expect(onSelectionChange).toHaveBeenLastCalledWith(rows)
    expect(screen.getByText('3 seleccionadas')).toBeInTheDocument()
  })

  it('shows an empty state, different when a search hides everything', async () => {
    const { unmount } = render(<DataTable columns={columns} data={[]} empty="Aún no hay reservas" />)
    expect(screen.getByText('Aún no hay reservas')).toBeInTheDocument()
    unmount()

    render(<DataTable columns={columns} data={rows} enableSearch />)
    await userEvent.type(screen.getByRole('searchbox'), 'zzz')
    expect(screen.getByText('Nada coincide con los filtros. Prueba con otra búsqueda.')).toBeInTheDocument()
  })
})

describe('DataTable (server pagination)', () => {
  function ServerHarness({ onPage }: { onPage: (p: PaginationState) => void }) {
    const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 })
    return (
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(r) => r.id}
        server={{
          rowCount: 60,
          pagination,
          onPaginationChange: (updater) => {
            const next = typeof updater === 'function' ? updater(pagination) : updater
            setPagination(next)
            onPage(next)
          },
        }}
      />
    )
  }

  it('shows the server total and asks for the next page', async () => {
    const onPage = vi.fn()
    render(<ServerHarness onPage={onPage} />)

    expect(screen.getByText('60 registros')).toBeInTheDocument()
    expect(screen.getByText('Página 1 de 3')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Página siguiente' }))
    expect(onPage).toHaveBeenLastCalledWith({ pageIndex: 1, pageSize: 25 })
    expect(screen.getByText('Página 2 de 3')).toBeInTheDocument()
  })
})
