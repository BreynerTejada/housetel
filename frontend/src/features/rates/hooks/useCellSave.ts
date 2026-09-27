import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { errorMessage } from '@/lib/errors'
import { invalidatePrices, postBulk, type GridResponse, type GridRow } from '../api'
import { applyCellChange, cellPayload, restoreCell, type CellChange } from '../lib/grid-utils'

const keyOf = (change: CellChange) => `${change.roomTypeId}:${change.date}:${change.field}`
const CELL_MUTATION = ['rates', 'grid', 'cell'] as const

/**
 * Saves one grid cell (`POST grid/bulk/` for a single night, `source: "manual"`). The cell changes at once;
 * if saving fails it gets its previous value back and the reason shows in a toast. `onSaved` receives the
 * audit event of each saved edit (for undo). Once the last pending cell is saved every grid is refetched:
 * derived plans follow the new base price and the server has the final word (rounding, sources).
 */
export function useCellSave({
  queryKey,
  planId,
  onSaved,
}: {
  queryKey: QueryKey
  planId: string | null
  onSaved: (auditEventId: string) => void
}) {
  const { t } = useTranslation('rates')
  const queryClient = useQueryClient()
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set())

  const mutation = useMutation({
    mutationKey: CELL_MUTATION,
    mutationFn: (change: CellChange) => postBulk(cellPayload(change, planId ?? '')),
    onMutate: async (change): Promise<{ original: GridRow | undefined }> => {
      setPending((current) => new Set(current).add(keyOf(change)))
      await queryClient.cancelQueries({ queryKey })
      const grid = queryClient.getQueryData<GridResponse>(queryKey)
      const original = grid?.room_types.find((rt) => rt.id === change.roomTypeId)?.rows.find((row) => row.date === change.date)
      if (grid) queryClient.setQueryData(queryKey, applyCellChange(grid, change))
      return { original }
    },
    onError: (error, change, context) => {
      const grid = queryClient.getQueryData<GridResponse>(queryKey)
      if (grid && context?.original) queryClient.setQueryData(queryKey, restoreCell(grid, change, context.original))
      toast.error(errorMessage(error, t))
    },
    onSuccess: (result) => {
      if (result.audit_event_id) onSaved(result.audit_event_id)
    },
    onSettled: (_result, _error, change) => {
      setPending((current) => {
        const next = new Set(current)
        next.delete(keyOf(change))
        return next
      })
      // a refetch while other cells are still saving would bring their old values back for a moment
      if (queryClient.isMutating({ mutationKey: CELL_MUTATION }) === 1) void invalidatePrices(queryClient)
    },
  })

  return { save: (change: CellChange) => mutation.mutate(change), pending }
}
