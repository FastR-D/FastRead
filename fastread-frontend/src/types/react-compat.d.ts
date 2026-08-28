import type * as React from 'react'

declare global {
  namespace JSX {
    type IntrinsicElements = React.JSX.IntrinsicElements
  }
}

declare module 'react' {
  // The generic parameter must match React's declaration for interface merging.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface SVGProps<T> {
    t?: string
    'p-id'?: string
  }
}

export {}
