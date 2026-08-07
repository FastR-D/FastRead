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
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useCallback, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import {
  type DownloaderCookieStatus,
  getDownloaderCookie,
  getDownloaderCookieStatus,
  updateDownloaderCookie,
} from '@/services/downloader'
import { useParams } from 'react-router-dom'
import { videoPlatforms } from '@/constant/note.ts'
import { CheckCircle2, Clipboard, RefreshCw, ShieldAlert, ShieldCheck, Upload } from 'lucide-react'

const CookieSchema = z.object({
  cookie: z.string().min(10, '请填写有效 Cookie'),
})

function parseCookieCount(cookie: string) {
  return cookie.split(';').map(part => part.trim()).filter(Boolean).length
}

function formatUpdatedAt(value?: string | null) {
  if (!value) return '尚未同步'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const DownloaderForm = () => {
  const form = useForm({
    resolver: zodResolver(CookieSchema),
    defaultValues: { cookie: '' },
  })
  const { id } = useParams()
  const platform = videoPlatforms.find(item => item.value === id)

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<DownloaderCookieStatus | null>(null)
  const cookieValue = form.watch('cookie')
  const localCookieCount = useMemo(() => parseCookieCount(cookieValue || ''), [cookieValue])

  const refreshStatus = useCallback(async (platformId?: string) => {
    if (!platformId) return
    setStatus(await getDownloaderCookieStatus(platformId))
  }, [])

  useEffect(() => {
    const loadCookie = async () => {
      setLoading(true)
      try {
        const res = await getDownloaderCookie(id)
        const cookie = res?.cookie || ''
        form.reset({ cookie })
        await refreshStatus(id)
      } catch (e) {
        toast.error('加载 Cookie 失败: ' + e)
        form.reset({ cookie: '' })
        setStatus(null)
      } finally {
        setLoading(false)
      }
    }

    if (id) loadCookie()
  }, [form, id, refreshStatus])

  const onSubmit = async values => {
    setSaving(true)
    try {
      await updateDownloaderCookie({
        platform: id,
        cookie: String(values.cookie),
      })
      await refreshStatus(id)
      toast.success('Cookie 已同步到后端')
    } catch {
      toast.error('Cookie 同步失败')
    } finally {
      setSaving(false)
    }
  }

  const pasteFromClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (!text.trim()) {
        toast.error('剪贴板为空')
        return
      }
      form.setValue('cookie', text.trim(), { shouldDirty: true, shouldValidate: true })
      toast.success(`已从剪贴板读取 ${parseCookieCount(text)} 项 Cookie`)
    } catch {
      toast.error('无法读取剪贴板，请手动粘贴')
    }
  }

  if (loading) return <div className="p-6 text-sm text-slate-500">加载 Cookie 配置...</div>

  return (
    <div className="h-full overflow-auto bg-white">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="mx-auto flex max-w-4xl flex-col gap-5 p-6">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-5">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold text-slate-900">{platform?.label || '视频平台'} Cookie 同步</h1>
                {status?.valid_looking ? (
                  <Badge className="bg-emerald-600 hover:bg-emerald-600">
                    <ShieldCheck className="mr-1 h-3.5 w-3.5" />
                    可用
                  </Badge>
                ) : (
                  <Badge variant={status?.configured ? 'secondary' : 'outline'}>
                    <ShieldAlert className="mr-1 h-3.5 w-3.5" />
                    {status?.configured ? '需检查' : '未同步'}
                  </Badge>
                )}
              </div>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                前端会把你粘贴的 Cookie 保存到后端下载器配置，用于解析需要登录态的抖音精选视频。
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={() => refreshStatus(id)} className="gap-2">
              <RefreshCw className="h-4 w-4" />
              刷新状态
            </Button>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
              <div className="text-xs font-medium text-slate-500">后端 Cookie 数量</div>
              <div className="mt-1 text-2xl font-semibold text-slate-900">{status?.cookie_count ?? 0}</div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
              <div className="text-xs font-medium text-slate-500">当前输入数量</div>
              <div className="mt-1 text-2xl font-semibold text-slate-900">{localCookieCount}</div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
              <div className="text-xs font-medium text-slate-500">最近同步</div>
              <div className="mt-2 text-sm font-medium text-slate-800">{formatUpdatedAt(status?.updated_at)}</div>
            </div>
          </div>

          {status && (
            <div
              className={`rounded-lg border px-4 py-3 text-sm ${
                status.valid_looking
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                  : status.configured
                    ? 'border-amber-200 bg-amber-50 text-amber-800'
                    : 'border-neutral-200 bg-neutral-50 text-neutral-600'
              }`}
            >
              <div className="flex items-start gap-2">
                {status.valid_looking ? <CheckCircle2 className="mt-0.5 h-4 w-4" /> : <ShieldAlert className="mt-0.5 h-4 w-4" />}
                <span>
                  {status.valid_looking
                    ? status.warning_message
                      ? `Cookie 已同步，包含 ${status.cookie_count} 项，可用于后端下载器。提示：${status.warning_message}`
                      : `Cookie 已同步，包含 ${status.cookie_count} 项，可用于后端下载器。`
                    : status.configured
                      ? `Cookie 已保存，但缺少 ${status.missing_keys.join('、') || '关键字段'}，建议重新复制完整 Cookie。`
                      : 'Cookie 未同步，抖音精选视频解析可能失败。'}
                </span>
              </div>
            </div>
          )}

          <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm leading-6 text-sky-900">
            普通 Web 页面不能直接读取 douyin.com 的浏览器 Cookie。请先在浏览器登录抖音精选，打开开发者工具或浏览器 Cookie 管理器复制
            <span className="font-medium"> name=value; name=value </span>
            格式的 Cookie，再粘贴到这里同步到后端。
          </div>

          <FormField
            control={form.control}
            name="cookie"
            render={({ field }) => (
              <FormItem className="flex flex-col gap-2">
                <FormLabel>Cookie</FormLabel>
                <FormControl>
                  <Textarea
                    {...field}
                    className="min-h-44 resize-y font-mono text-xs leading-5"
                    placeholder="ttwid=...; msToken=...; sessionid=..."
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" onClick={pasteFromClipboard} className="gap-2">
              <Clipboard className="h-4 w-4" />
              从剪贴板导入
            </Button>
            <Button type="submit" disabled={saving} className="gap-2">
              <Upload className="h-4 w-4" />
              {saving ? '同步中...' : '同步到后端'}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  )
}

export default DownloaderForm
