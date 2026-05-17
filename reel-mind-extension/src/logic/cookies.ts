import { setDownloaderCookie } from './api'
import browser from 'webextension-polyfill'
import type { Platform } from './types'

type CookiePlatform = Extract<Platform, 'douyin'>

// 后端期望的 cookie 字符串格式：name=value; name=value; ...
// 当前入口只暴露抖音精选，其他平台 cookie 兼容层暂不展示。
const COOKIE_URLS = {
  douyin: 'https://www.douyin.com/',
} satisfies Record<CookiePlatform, string>

export const SUPPORTED_COOKIE_PLATFORMS: CookiePlatform[] = [
  'douyin',
]

export async function readBrowserCookies(platform: CookiePlatform): Promise<string> {
  const url = COOKIE_URLS[platform]
  const list = await browser.cookies.getAll({ url })
  return list.map(c => `${c.name}=${c.value}`).join('; ')
}

export async function syncCookieToBackend(platform: CookiePlatform): Promise<{ ok: boolean, count: number, error?: string }> {
  try {
    const cookieStr = await readBrowserCookies(platform)
    if (!cookieStr)
      return { ok: false, count: 0, error: '当前浏览器没有该域名的 cookie，先在浏览器内登录目标站点' }
    const count = cookieStr.split('; ').length
    await setDownloaderCookie(platform, cookieStr)
    return { ok: true, count }
  }
  catch (e) {
    return { ok: false, count: 0, error: (e as Error).message }
  }
}
