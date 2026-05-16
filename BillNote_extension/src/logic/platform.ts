import type { Platform } from './types'

// 与 backend/app/validators/video_url_validator.py 保持一致
export function detectPlatform(url: string | undefined | null): Platform | null {
  if (!url)
    return null
  try {
    const { hostname } = new URL(url)
    if (hostname === 'douyin.com' || hostname.endsWith('.douyin.com'))
      return 'douyin'
  }
  catch {
    if (/https?:\/\/[^/\s]*douyin\.com\//.test(url))
      return 'douyin'
  }
  return null
}

export function isDouyinUrl(url: string | undefined | null): boolean {
  return detectPlatform(url) === 'douyin'
}

export const PLATFORM_LABELS: Record<Platform, string> = {
  douyin: '抖音精选',
}
