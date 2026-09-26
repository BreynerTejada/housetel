import { Outlet } from 'react-router'

/** No chrome at all: simulated payment gateway, embeddable widget. */
export function BareLayout() {
  return (
    <div className="public-shell min-h-dvh bg-bg">
      <Outlet />
    </div>
  )
}
