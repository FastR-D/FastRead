import request from '@/utils/request.ts'

export interface DownloaderCookieStatus {
  platform: string
  configured: boolean
  cookie_count: number
  length: number
  updated_at?: string | null
  valid_looking: boolean
  missing_keys: string[]
}

export const getDownloaderCookie = async (id?: string) => {
  return await request.get('/get_downloader_cookie/' + id)
}

export const updateDownloaderCookie = async (data: { cookie: string; platform: any }) => {
  return await request.post('/update_downloader_cookie', data)
}

export const getDownloaderCookieStatus = async (id?: string): Promise<DownloaderCookieStatus> => {
  return await request.get('/downloader_cookie_status/' + id)
}
