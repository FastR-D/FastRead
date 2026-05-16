import type { Platform } from './types'

// 与 backend/app/validators/video_url_validator.py 保持一致
export function detectPlatform(url: string | undefined | null): Platform | null {
  if (!url)
    return null
  try {
    const { hostname } = new URL(url)
    if (hostname === 'douyin.com' || hostname.endsWith('.douyin.com'))
      return 'douyin'
    if (hostname === 'bilibili.com' || hostname.endsWith('.bilibili.com') || hostname === 'b23.tv')
      return 'bilibili'
    if (hostname === 'kuaishou.com' || hostname.endsWith('.kuaishou.com') || hostname.endsWith('.chenzhongtech.com'))
      return 'kuaishou'
  }
  catch {
    if (/https?:\/\/[^/\s]*douyin\.com\//.test(url))
      return 'douyin'
    if (/https?:\/\/[^/\s]*(bilibili\.com|b23\.tv)\//.test(url))
      return 'bilibili'
    if (/https?:\/\/[^/\s]*(kuaishou\.com|chenzhongtech\.com)\//.test(url))
      return 'kuaishou'
  }
  return null
}

export function isDouyinUrl(url: string | undefined | null): boolean {
  return detectPlatform(url) === 'douyin'
}

export const PLATFORM_LABELS: Record<Platform, string> = {
  douyin: '抖音精选',
  bilibili: 'B站',
  kuaishou: '快手',
}
