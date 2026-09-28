import ReactMarkdown, { type Components } from 'react-markdown'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'

/**
 * The assistant's Markdown (paragraphs, lists, bold, links, inline code). Raw HTML and images are not
 * rendered; links inside the app stay in the SPA, the rest open in a new tab.
 */
const components: Components = {
  p: ({ children }) => <p className="leading-relaxed [&:not(:first-child)]:mt-2">{children}</p>,
  ul: ({ children }) => <ul className="mt-2 flex list-disc flex-col gap-1 pl-5 marker:text-subtle">{children}</ul>,
  ol: ({ children }) => <ol className="mt-2 flex list-decimal flex-col gap-1 pl-5 marker:text-subtle">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-bold text-fg">{children}</strong>,
  code: ({ children }) => <code className="num rounded bg-surface-2 px-1 py-0.5 text-[0.92em]">{children}</code>,
  a: ({ href, children }) =>
    href?.startsWith('/') ? (
      <Link to={href} className="font-semibold text-accent-ink underline underline-offset-2">
        {children}
      </Link>
    ) : (
      <a href={href} target="_blank" rel="noreferrer noopener" className="font-semibold text-accent-ink underline underline-offset-2">
        {children}
      </a>
    ),
  img: () => null,
}

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn('text-sm text-fg', className)}>
      <ReactMarkdown components={components} skipHtml>
        {children}
      </ReactMarkdown>
    </div>
  )
}
