import type { TopbarItem } from '@/app/extensions'
import { VerifyEmailChip } from './components/VerifyEmailChip'

// Owner: P2. Reminder to confirm the email address; renders nothing once it is verified.
export const topbarItems: TopbarItem[] = [{ id: 'team-verify-email', order: 4, Component: VerifyEmailChip }]
