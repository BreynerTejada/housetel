import { Fragment } from 'react'

const URL_RE = /(https?:\/\/[^\s<>"')]+[^\s<>"').,;:!?])/g

/** Message text with its web links clickable (the text itself is never parsed as HTML). */
export function Linkified({ text }: { text: string }) {
  const parts = text.split(URL_RE)
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <a
            key={index}
            href={part}
            target="_blank"
            rel="noopener noreferrer"
            className="break-all text-accent-ink underline underline-offset-2 hover:text-accent"
          >
            {part}
          </a>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </>
  )
}
