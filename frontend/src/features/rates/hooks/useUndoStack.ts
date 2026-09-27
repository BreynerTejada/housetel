import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { api, isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { auditKey, undoAuditEvent } from '../api'

/**
 * Stack of the audit events of this session's grid edits, undone last-first through the generic endpoint of
 * the control center (`POST /api/v1/control/audit/{id}/undo/`). While that endpoint does not exist (404) or
 * the user lacks `control.audit_undo`, undo stays disabled.
 */
export function useUndoStack({ onUndone }: { onUndone: () => void }) {
  const { t } = useTranslation('rates')
  const allowed = useCan('control.audit_undo')
  const [stack, setStack] = useState<string[]>([])
  const [missing, setMissing] = useState(false)
  const lastId = stack.at(-1) ?? null

  const probe = useQuery({
    queryKey: auditKey(lastId ?? 'none'),
    queryFn: () => api.get<unknown>(`/control/audit/${lastId}/`, { authRedirect: false }),
    enabled: lastId !== null && allowed && !missing,
    retry: false,
    staleTime: Infinity,
  })
  const endpointMissing = missing || (probe.isError && isApiError(probe.error) && probe.error.status === 404)

  const mutation = useMutation({
    mutationFn: (id: string) => undoAuditEvent(id),
    onSuccess: () => {
      setStack((current) => current.slice(0, -1))
      toast.success(t('undo.done'))
      onUndone()
    },
    onError: (error) => {
      if (isApiError(error) && error.status === 404) setMissing(true)
      toast.error(isApiError(error) && error.status === 404 ? t('undo.unavailable') : errorMessage(error, t))
    },
  })

  return {
    push: (id: string) => setStack((current) => [...current, id]),
    lastId,
    allowed,
    canUndo: lastId !== null && allowed && probe.isSuccess && !endpointMissing && !mutation.isPending,
    endpointMissing: lastId !== null && endpointMissing,
    pending: mutation.isPending,
    undo: () => lastId && mutation.mutate(lastId),
  }
}

export type UndoStack = ReturnType<typeof useUndoStack>
