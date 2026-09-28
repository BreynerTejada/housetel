import type { HkTask } from '../api'

const OPEN = new Set(['pending', 'in_progress'])

/** The task of a room that matters now: the first open one, else the latest that was not cancelled. */
export function leadTask(tasks: HkTask[]): HkTask | undefined {
  return tasks.find((task) => OPEN.has(task.status)) ?? tasks.find((task) => task.status !== 'cancelled')
}
