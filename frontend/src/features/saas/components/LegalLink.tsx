import type { ReactNode } from 'react'
import { Link } from 'react-router'

/**
 * A link to one of Housetel's legal documents inside a consent text (`<Trans components>`). It opens in a new
 * tab so the form being filled (signup, checkout, online check-in) keeps what the person already typed.
 */
export function LegalLink({ to, children }: { to: string; children?: ReactNode }) {
  return (
    <Link to={to} target="_blank" rel="noopener" className="font-semibold text-accent-ink underline underline-offset-2 hover:no-underline">
      {children}
    </Link>
  )
}
