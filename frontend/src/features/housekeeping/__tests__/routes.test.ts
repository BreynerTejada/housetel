import { describe, expect, it } from 'vitest'
import { commands } from '../commands'
import { routes } from '../routes'

describe('housekeeping routes and commands', () => {
  it('serves real pages at the paths of the plan (§E), loaded lazily', async () => {
    const loaded = await Promise.all(
      (routes.app ?? []).map(async (route) => {
        const load = route.lazy as (() => Promise<{ Component?: unknown }>) | undefined
        const module = await load?.()
        return [route.path, typeof module?.Component] as const
      }),
    )
    expect(loaded).toEqual([
      ['housekeeping', 'function'],
      ['housekeeping/mine', 'function'],
      ['maintenance', 'function'],
      ['settings/housekeeping', 'function'],
    ])
  })

  it('offers "my rooms" and "report damage" in the command palette to people who clean', () => {
    const navigate = (to: string) => visited.push(to)
    const visited: string[] = []
    for (const command of commands) command.perform({ navigate })
    expect(commands.map(({ id, permission }) => [id, permission])).toEqual([
      ['housekeeping.mine', 'housekeeping.work'],
      ['housekeeping.report', 'housekeeping.work'],
    ])
    expect(visited).toEqual(['/app/housekeeping/mine', '/app/maintenance?new=1'])
  })
})
