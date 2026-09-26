import { RotateCcw } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { isRouteErrorResponse, useRouteError } from 'react-router'
import { Button } from '@/components/ui/button'
import { NotFound } from './NotFound'

/** Error boundary of the route tree. Inside a shell it renders in the outlet, so navigation stays. */
export function RouteError({ home = '/' }: { home?: string }) {
  const { t } = useTranslation()
  const error = useRouteError()

  useEffect(() => {
    console.error('Route error', error)
  }, [error])

  if (isRouteErrorResponse(error) && error.status === 404) return <NotFound home={home} />

  return (
    <section role="alert" className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center px-6 py-20 text-center">
      <h1 className="text-2xl text-fg">{t('routeError.title')}</h1>
      <p className="mt-2 text-muted">{t('routeError.description')}</p>
      <Button variant="secondary" className="mt-6" onClick={() => window.location.reload()}>
        <RotateCcw aria-hidden />
        {t('routeError.reload')}
      </Button>
    </section>
  )
}
