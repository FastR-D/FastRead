declare module 'react-syntax-highlighter' {
  import type { ComponentType, CSSProperties, ElementType } from 'react'

  export interface SyntaxHighlighterProps {
    children: string
    language?: string
    style?: Record<string, CSSProperties>
    PreTag?: ElementType
    customStyle?: CSSProperties
    [attribute: `data-${string}`]: string | undefined
  }

  export const Prism: ComponentType<SyntaxHighlighterProps>
}

declare module 'react-syntax-highlighter/dist/esm/styles/prism' {
  import type { CSSProperties } from 'react'
  export const atomDark: Record<string, CSSProperties>
}
