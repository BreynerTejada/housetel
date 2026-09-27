import { useMemo } from 'react'
import {
  useRatesList,
  useRoomTypeOptions,
  type CancellationPolicy,
  type RatePlan,
  type RoomTypeDefaults,
  type RoomTypeOption,
} from '../api'
import { planFamilies } from '../lib/plans'

/** What the plans page shows everywhere: plans (grouped in families), categories, default prices, policies. */
export function usePlansData() {
  const plans = useRatesList<RatePlan>('rate-plans')
  const roomTypes = useRoomTypeOptions()
  const defaults = useRatesList<RoomTypeDefaults>('room-type-defaults')
  const policies = useRatesList<CancellationPolicy>('cancellation-policies')

  const value = useMemo(() => {
    const planList = plans.data ?? []
    const typeList = [...(roomTypes.data ?? [])].sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code))
    const defaultsByKey = new Map((defaults.data ?? []).map((item) => [defaultsKey(item.room_type, item.rate_plan), item]))
    return {
      plans: planList,
      families: planFamilies(planList),
      basePlans: planList.filter((plan) => plan.kind === 'base').sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code)),
      roomTypes: typeList,
      roomTypeById: new Map(typeList.map((roomType) => [roomType.id, roomType])),
      policies: policies.data ?? [],
      policyById: new Map((policies.data ?? []).map((policy) => [policy.id, policy])),
      defaultsFor: (roomTypeId: string, planId: string) => defaultsByKey.get(defaultsKey(roomTypeId, planId)) ?? null,
    }
  }, [plans.data, roomTypes.data, defaults.data, policies.data])

  const queries = [plans, roomTypes, defaults, policies]
  return {
    ...value,
    isPending: queries.some((query) => query.isPending),
    error: queries.find((query) => query.isError)?.error ?? null,
    refetch: () => queries.forEach((query) => void query.refetch()),
  }
}

export type PlansData = ReturnType<typeof usePlansData>

const defaultsKey = (roomTypeId: string, planId: string) => `${roomTypeId}:${planId}`

/** Categories a plan sells, in category order. */
export function soldRoomTypes(plan: RatePlan, roomTypes: RoomTypeOption[]): RoomTypeOption[] {
  return roomTypes.filter((roomType) => plan.room_types.includes(roomType.id))
}
