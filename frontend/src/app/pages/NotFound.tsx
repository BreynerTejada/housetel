import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'

export function NotFound({ home = '/' }: { home?: string }) {
  const { t } = useTranslation()
  return (
    <section className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center px-6 py-20 text-center">
      <p className="eyebrow num">{t('notFound.code')}</p>
      <h1 className="mt-3 text-2xl text-fg">{t('notFound.title')}</h1>
      <p className="mt-2 text-muted">{t('notFound.description')}</p>
      <Button asChild variant="secondary" className="mt-6">
        <Link to={home}>{t('notFound.cta')}</Link>
      </Button>
    </section>
  )
}

export default NotFound
