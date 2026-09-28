import type { Lang } from '@/lib/format'
import type { EffectiveTemplate, SendChannel } from '../api'

export interface TemplateOption {
  code: string
  label: string
  /** A Housetel lifecycle template (else a custom one of the hotel). */
  system: boolean
  /** At least one variant (of `channel`, when given) is switched on. */
  active: boolean
}

/** One option per template code, in the API order (lifecycle first, then the hotel's own). */
export function templateOptions(templates: EffectiveTemplate[] | undefined, lang: Lang, channel?: SendChannel): TemplateOption[] {
  const byCode = new Map<string, TemplateOption>()
  for (const template of templates ?? []) {
    const current = byCode.get(template.code)
    const counts = !channel || template.channel === channel
    byCode.set(template.code, {
      code: template.code,
      label: template.label[lang] || template.label.es || template.code,
      system: template.is_system_code,
      active: (current?.active ?? false) || (counts && template.is_active),
    })
  }
  return [...byCode.values()]
}

/** "Oferta de spa" → "oferta_de_spa": the code of a new custom template (lowercase, digits, underscores). */
export function slugifyCode(name: string): string {
  const slug = name
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 60)
  if (!slug) return ''
  return /^[a-z]/.test(slug) ? slug : `t_${slug}`
}
