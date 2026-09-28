import { useParams } from 'react-router'
import { CheckoutView } from '../components/CheckoutView'
import { EngineShell } from '../components/EngineShell'

/** `/h/:slug/book` — checkout on the hotel's own booking engine. */
export default function EngineCheckoutPage() {
  const { slug = '' } = useParams()
  return <EngineShell slug={slug}>{() => <CheckoutView slug={slug} via="booking_engine" />}</EngineShell>
}
