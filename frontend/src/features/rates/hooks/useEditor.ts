import { useState } from 'react'

/** Open/close state of a create-or-edit dialog (`item === null` means creating). */
export function useEditor<T>() {
  const [state, setState] = useState<{ open: boolean; item: T | null; key: number }>({ open: false, item: null, key: 0 })
  return {
    open: state.open,
    item: state.item,
    /** Changes every time the dialog opens, so the form inside starts from fresh values. */
    key: state.key,
    create: () => setState((current) => ({ open: true, item: null, key: current.key + 1 })),
    edit: (item: T) => setState((current) => ({ open: true, item, key: current.key + 1 })),
    setOpen: (open: boolean) => setState((current) => ({ ...current, open })),
  }
}
