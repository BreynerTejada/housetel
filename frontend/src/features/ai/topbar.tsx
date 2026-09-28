import type { TopbarItem } from '@/app/extensions'
import { CopilotButton } from './components/CopilotButton'

// Topbar: the copilot button (plan C9). Visible with `ai.copilot`.
export const topbarItems: TopbarItem[] = [{ id: 'ai-copilot', order: 10, permission: 'ai.copilot', Component: CopilotButton }]
