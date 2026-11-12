import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import remarkGfm from 'remark-gfm'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import type { Components } from 'react-markdown'
import type { MarkdownProps } from './Markdown'

const components: Components = {
  a: props => <a {...props} className="fastui-link" target="_blank" rel="noreferrer" />,
  table: props => (
    <div className="fastui-table-scroll" role="region" aria-label="内容表格" tabIndex={0}>
      <table {...props} className="fastui-table w-full" />
    </div>
  ),
  pre: props => <pre {...props} className="max-w-full overflow-auto" />,
  img: props => <img {...props} className="h-auto max-w-full" />,
  blockquote: props => <blockquote {...props} className="fastui-section m-0 p-3 break-words" />,
  h1: props => <h1 {...props} className="fastui-heading text-xl" />,
  h2: props => <h2 {...props} className="fastui-heading text-lg" />,
  h3: props => <h3 {...props} className="fastui-heading text-base" />,
}

export default function MarkdownRenderer({
  math,
  gfm,
  components: overrides,
  ...props
}: MarkdownProps) {
  return (
    <ReactMarkdown
      {...props}
      components={{ ...components, ...overrides }}
      remarkPlugins={[...(gfm ? [remarkGfm] : []), ...(math ? [remarkMath] : [])]}
      rehypePlugins={math ? [rehypeKatex] : []}
    />
  )
}
