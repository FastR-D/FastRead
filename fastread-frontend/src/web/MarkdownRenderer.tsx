import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import remarkGfm from 'remark-gfm'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import type { MarkdownProps } from './Markdown'

export default function MarkdownRenderer({ math, gfm, ...props }: MarkdownProps) {
  return <ReactMarkdown {...props} remarkPlugins={[...(gfm ? [remarkGfm] : []), ...(math ? [remarkMath] : [])]} rehypePlugins={math ? [rehypeKatex] : []} />
}
