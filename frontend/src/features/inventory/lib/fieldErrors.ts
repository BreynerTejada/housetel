/**
 * The API's validation `fields` (`{field: [msgs]}`, nested for JSON fields such as `custom_values` or
 * `overrides`, numbered for lists) → one message per dotted key: `{"custom_values.minibar": "…"}`.
 */
export function flattenFieldErrors(fields: unknown): Record<string, string> {
  const flat: Record<string, string> = {}
  const visit = (value: unknown, key: string) => {
    if (typeof value === 'string') {
      if (key) flat[key] = flat[key] ? `${flat[key]} ${value}` : value
    } else if (Array.isArray(value)) {
      value.forEach((item, index) => visit(item, typeof item === 'string' || !key ? key || String(index) : `${key}.${index}`))
    } else if (value && typeof value === 'object') {
      for (const [child, nested] of Object.entries(value)) visit(nested, key ? `${key}.${child}` : child)
    }
  }
  if (fields && typeof fields === 'object' && !Array.isArray(fields)) visit(fields, '')
  return flat
}

/** Server errors without the ones of `keys` (and their nested keys): the user just edited those fields. */
export function withoutErrors(errors: Record<string, string>, keys: string[]): Record<string, string> {
  return Object.fromEntries(
    Object.entries(errors).filter(([key]) => !keys.some((edited) => key === edited || key.startsWith(`${edited}.`))),
  )
}
