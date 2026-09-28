import { useParams } from 'react-router'
import { ConfirmationView } from '../components/ConfirmationView'
import { EngineShell } from '../components/EngineShell'

/** `/h/:slug/booking/:code` — a booking made on the hotel's engine (the payment gateway returns here). */
export default function EngineConfirmationPage() {
  const { slug = '', code = '' } = useParams()
  return <EngineShell slug={slug}>{() => <ConfirmationView code={code.toUpperCase()} via="booking_engine" />}</EngineShell>
}
