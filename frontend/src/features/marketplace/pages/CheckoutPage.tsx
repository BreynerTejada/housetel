import { useParams } from 'react-router'
import { CheckoutView } from '../components/CheckoutView'

/** `/book/:slug` — checkout of a marketplace booking. */
export default function CheckoutPage() {
  const { slug = '' } = useParams()
  return <CheckoutView slug={slug} via="marketplace" />
}
