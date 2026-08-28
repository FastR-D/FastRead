import type { ElementType } from 'react'
import * as Icons from '@lobehub/icons'

export type LobeIconStyle = 'Color' | 'Text' | 'Outlined' | 'Glyph'
type IconElement = ElementType<{ size?: number }>
type IconWithVariants = IconElement & Partial<Record<LobeIconStyle, IconElement>>

function isIconElement(value: unknown): value is IconElement {
  return typeof value === 'function'
    || (typeof value === 'object' && value !== null && '$$typeof' in value)
}

export function resolveLobeIcon(name: string, style: LobeIconStyle) {
  const candidate: unknown = name ? Icons[name as keyof typeof Icons] : undefined
  if (!isIconElement(candidate)) return null

  const icon = candidate as IconWithVariants
  const variantCandidate: unknown = icon[style]
  return {
    Icon: icon as IconElement,
    Variant: isIconElement(variantCandidate) ? variantCandidate : undefined,
  }
}
