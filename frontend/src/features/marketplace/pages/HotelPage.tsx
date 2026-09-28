import { useParams } from 'react-router'
import { HotelView } from '../components/HotelView'

/** `/hotel/:slug` — a hotel on the Housetel marketplace. */
export default function HotelPage() {
  const { slug = '' } = useParams()
  return <HotelView slug={slug} via="marketplace" />
}
