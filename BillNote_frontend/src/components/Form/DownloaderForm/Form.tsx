// 下载器 Cookie 设置表单（最简化版）
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import {
  type DownloaderCookieStatus,
  getDownloaderCookie,
  getDownloaderCookieStatus,
  updateDownloaderCookie,
} from '@/services/downloader'
import { useParams } from 'react-router-dom'
import { videoPlatforms } from '@/constant/note.ts'

const CookieSchema = z.object({
  cookie: z.string().min(10, '请填写有效 Cookie'),
})

const DownloaderForm = () => {
  const form = useForm({
    resolver: zodResolver(CookieSchema),
    defaultValues: { cookie: '' },
  })
  const { id } = useParams()

  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<DownloaderCookieStatus | null>(null)

  const refreshStatus = async (platformId?: string) => {
    if (!platformId) return
    setStatus(await getDownloaderCookieStatus(platformId))
  }

  useEffect(() => {
    const loadCookie = async () => {
      setLoading(true) // 🔁 切换平台时显示 loading
      try {
        const res = await getDownloaderCookie(id)
        const cookie = res?.cookie || ''
        form.reset({ cookie }) // ✅ 正确重置表单值
        await refreshStatus(id)
      } catch (e) {
        toast.error('加载 Cookie 失败: ' + e)
        form.reset({ cookie: '' }) // ❗失败时也要清空旧值
        setStatus(null)
      } finally {
        setLoading(false)
      }
    }

    if (id) loadCookie()
  }, [id]) // 🔁 每当 id 变化时触发

  const onSubmit = async values => {
    try {
      await updateDownloaderCookie({
        platform: id,
        cookie: String(values.cookie),
      })
      await refreshStatus(id)
      toast.success('保存成功')
    } catch (e) {
      toast.error('保存失败')
    }
  }

  if (loading) return <div className="p-4">加载中...</div>

  return (
    <div className="max-w-xl p-4">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-lg font-bold">
              设置{videoPlatforms.find(item => item.value === id)?.label}下载器 Cookie
            </div>
            <Button type="button" variant="outline" size="sm" onClick={() => refreshStatus(id)}>
              刷新状态
            </Button>
          </div>

          <div className="rounded border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-800">
            Web 页面无法直接读取抖音 Cookie。推荐在浏览器扩展的弹窗中点击“同步 Cookie”：
            先登录抖音精选，然后打开“精选知识助手”扩展弹窗同步。这里保留手动粘贴入口作为兜底。
          </div>

          {status && (
            <div
              className={`rounded border px-3 py-2 text-sm ${
                status.valid_looking
                  ? 'border-green-200 bg-green-50 text-green-800'
                  : status.configured
                    ? 'border-amber-200 bg-amber-50 text-amber-800'
                    : 'border-neutral-200 bg-neutral-50 text-neutral-600'
              }`}
            >
              {status.valid_looking
                ? `Cookie 已配置，包含 ${status.cookie_count} 项。`
                : status.configured
                  ? `Cookie 已保存，但缺少 ${status.missing_keys.join('、') || '关键字段'}，建议在扩展弹窗重新同步。`
                  : 'Cookie 未配置，抖音精选视频解析可能失败。'}
            </div>
          )}

          <FormField
            control={form.control}
            name="cookie"
            render={({ field }) => (
              <FormItem className="flex flex-col gap-2">
                <FormLabel>Cookie</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="输入 Cookie" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button type="submit">保存</Button>
        </form>
      </Form>
    </div>
  )
}

export default DownloaderForm
