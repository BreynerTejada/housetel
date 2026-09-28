import type { TopbarItem } from '@/app/extensions'
import { BillingStatusItem } from './components/BillingStatusItem'

// Owner: C11. Subscription state of the organization (trial days, past due, suspended) with the way to pay.
export const topbarItems: TopbarItem[] = [{ id: 'saas-billing-status', order: 5, Component: BillingStatusItem }]
