import { useParams } from 'react-router'
import { ConfirmationView } from '../components/ConfirmationView'

/** `/booking/:code/confirmed` — a marketplace booking after checkout (and after the payment gateway). */
export default function ConfirmationPage() {
  const { code = '' } = useParams()
  return <ConfirmationView code={code.toUpperCase()} via="marketplace" />
}
