import { Eraser } from 'lucide-react'
import { useEffect, useImperativeHandle, useRef, type Ref } from 'react'
import SignaturePadLib from 'signature_pad'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface SignaturePadHandle {
  isEmpty: () => boolean
  /** PNG with a transparent background (the server checks that something was drawn). */
  toDataURL: () => string
  clear: () => void
}

const INK = '#1f1c19'

/**
 * A finger/stylus signature box on a paper-white card (same look in light and dark mode, so the ink always
 * shows). The canvas keeps its drawing when the phone rotates.
 */
export function SignaturePad({
  ref,
  onChange,
  invalid = false,
  describedBy,
}: {
  ref?: Ref<SignaturePadHandle>
  onChange?: (empty: boolean) => void
  invalid?: boolean
  describedBy?: string
}) {
  const { t } = useTranslation('guestportal')
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const padRef = useRef<SignaturePadLib | null>(null)
  const onChangeRef = useRef(onChange)

  useEffect(() => {
    onChangeRef.current = onChange
  })

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const pad = new SignaturePadLib(canvas, { penColor: INK, minWidth: 0.9, maxWidth: 2.6 })
    padRef.current = pad
    const resize = () => {
      const data = pad.toData()
      const ratio = Math.max(window.devicePixelRatio || 1, 1)
      canvas.width = canvas.offsetWidth * ratio
      canvas.height = canvas.offsetHeight * ratio
      canvas.getContext('2d')?.scale(ratio, ratio)
      pad.clear()
      pad.fromData(data)
    }
    resize()
    const onEnd = () => onChangeRef.current?.(pad.isEmpty())
    pad.addEventListener('endStroke', onEnd)
    window.addEventListener('resize', resize)
    return () => {
      pad.removeEventListener('endStroke', onEnd)
      pad.off()
      window.removeEventListener('resize', resize)
      padRef.current = null
    }
  }, [])

  useImperativeHandle(
    ref,
    () => ({
      isEmpty: () => padRef.current?.isEmpty() ?? true,
      toDataURL: () => padRef.current?.toDataURL('image/png') ?? '',
      clear: () => {
        padRef.current?.clear()
        onChangeRef.current?.(true)
      },
    }),
    [],
  )

  return (
    <div className="grid gap-2">
      <div
        className={cn(
          'relative overflow-hidden rounded-xl border-2 border-dashed bg-white shadow-xs',
          invalid ? 'border-danger' : 'border-border-strong',
        )}
      >
        <canvas
          ref={canvasRef}
          role="img"
          aria-label={t('checkin.signature.pad')}
          aria-describedby={describedBy}
          className="block h-44 w-full touch-none sm:h-52"
        />
        <div aria-hidden className="pointer-events-none absolute inset-x-6 bottom-10 flex items-end gap-2 text-[#948c81]">
          <span className="text-lg leading-none">×</span>
          <span className="mb-1 flex-1 border-b border-[#d5cdc2]" />
        </div>
        <p aria-hidden className="pointer-events-none absolute right-4 bottom-3 text-xs text-[#948c81]">
          {t('checkin.signature.padHint')}
        </p>
      </div>
      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={() => {
          padRef.current?.clear()
          onChangeRef.current?.(true)
        }}>
          <Eraser aria-hidden />
          {t('checkin.signature.clear')}
        </Button>
      </div>
    </div>
  )
}
