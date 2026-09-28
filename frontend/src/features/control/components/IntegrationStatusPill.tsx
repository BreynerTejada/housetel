import { CircleCheck, CircleDashed, CircleOff, KeyRound, OctagonAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import type { Integration } from '../api'

/** Connection state of an integration: off, missing credentials (real mode), OK, error or not tested. */
export function IntegrationStatusPill({ integration }: { integration: Integration }) {
  const { t } = useTranslation('control')
  if (!integration.enabled) {
    return (
      <Badge tone="stone">
        <CircleOff aria-hidden />
        {t('integrations.status.disabled')}
      </Badge>
    )
  }
  if (integration.mode === 'real' && integration.missing_required.length > 0) {
    return (
      <Badge tone="warning">
        <KeyRound aria-hidden />
        {t('integrations.status.missing')}
      </Badge>
    )
  }
  if (integration.status === 'ok') {
    return (
      <Badge tone="success">
        <CircleCheck aria-hidden />
        {t('integrations.status.ok')}
      </Badge>
    )
  }
  if (integration.status === 'error') {
    return (
      <Badge tone="danger">
        <OctagonAlert aria-hidden />
        {t('integrations.status.error')}
      </Badge>
    )
  }
  return (
    <Badge tone="neutral">
      <CircleDashed aria-hidden />
      {t('integrations.status.unknown')}
    </Badge>
  )
}
