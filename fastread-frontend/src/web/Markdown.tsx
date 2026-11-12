import { lazy, Suspense } from 'react'
import type { Components } from 'react-markdown'

export type MarkdownProps = {
  children: string
  math?: boolean
  gfm?: boolean
  components?: Components
}
const Renderer = lazy(() => import('./MarkdownRenderer'))

export default function Markdown(props: MarkdownProps) {
  return (
    <Suspense fallback={<div className="break-words whitespace-pre-wrap">{props.children}</div>}>
      <Renderer {...props} />
    </Suspense>
  )
}
