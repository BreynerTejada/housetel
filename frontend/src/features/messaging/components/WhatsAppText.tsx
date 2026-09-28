import { Linkified } from './Linkified'

const BOLD_RE = /(\*[^*\n]+\*)/g

/** WhatsApp text as the guest's phone shows it: `*bold*` in bold and web links clickable (never HTML). */
export function WhatsAppText({ text }: { text: string }) {
  const parts = text.split(BOLD_RE)
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <strong key={index} className="font-bold">
            <Linkified text={part.slice(1, -1)} />
          </strong>
        ) : (
          <Linkified key={index} text={part} />
        ),
      )}
    </>
  )
}
