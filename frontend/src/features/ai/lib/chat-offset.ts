import { useEffect, type RefObject } from 'react'

/**
 * Public pages with a bar glued to the bottom of the screen (the checkout's total + confirm button on phones)
 * tell the chat bubble how tall it is, so the bubble floats above it instead of covering the button (plan P6).
 * The bubble reads `var(--public-chat-offset)`; nothing else needs to know about it.
 */
export const CHAT_OFFSET_VAR = '--public-chat-offset'

/** While `active`, keeps `--public-chat-offset` equal to the height of `ref` (0 when inactive or unmounted). */
export function useChatOffset(ref: RefObject<HTMLElement | null>, active: boolean) {
  useEffect(() => {
    const root = document.documentElement
    const element = ref.current
    if (!active || !element) {
      root.style.removeProperty(CHAT_OFFSET_VAR)
      return
    }
    const update = () => root.style.setProperty(CHAT_OFFSET_VAR, `${Math.ceil(element.getBoundingClientRect().height)}px`)
    update()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update)
    observer?.observe(element)
    return () => {
      observer?.disconnect()
      root.style.removeProperty(CHAT_OFFSET_VAR)
    }
  }, [ref, active])
}
