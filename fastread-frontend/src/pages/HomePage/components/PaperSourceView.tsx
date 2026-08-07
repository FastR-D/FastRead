import { useEffect, useMemo, useState } from 'react'
import { ExternalLink, FileSearch, Files, Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { resolve_backend_resource_url } from '@/services/note'
import type { Task } from '@/store/taskStore'
import { cn } from '@/lib/utils'

export default function PaperSourceView({ task }: { task: Task | null }) {
  const paper = task?.paperDocument
  const [query, setQuery] = useState('')
  const [activePage, setActivePage] = useState(1)

  useEffect(() => {
    setQuery('')
    setActivePage(paper?.pages?.[0]?.page || 1)
  }, [paper?.id])

  const visiblePages = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return paper?.pages || []
    return (paper?.pages || []).filter(page =>
      page.text.toLowerCase().includes(keyword) || String(page.page) === keyword
    )
  }, [paper?.pages, query])

  const selectedPage = (paper?.pages || []).find(page => page.page === activePage)
    || visiblePages[0]
    || paper?.pages?.[0]
  const sourceHref = resolve_backend_resource_url(paper?.pdf_url || paper?.resolved_source_url || paper?.source_url)

  if (!task || !paper) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center">
        <div>
          <FileSearch className="mx-auto h-9 w-9 text-slate-300" />
          <p className="mt-3 text-sm font-medium text-slate-700">尚无分页论文原文</p>
          <p className="mt-1 text-xs text-slate-500">请先导入 PDF，或提交包含可访问 PDF 的论文详情页。</p>
        </div>
      </div>
    )
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-[220px_minmax(0,1fr)] bg-slate-50/50">
      <aside className="flex min-h-0 flex-col border-r border-slate-200 bg-white">
        <div className="border-b border-slate-200 p-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-800">
            <Files className="h-4 w-4" />
            分页原文
          </div>
          <div className="relative mt-2">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <Input
              value={query}
              onChange={event => setQuery(event.target.value)}
              className="h-8 pl-8 text-xs"
              placeholder="搜索页内文字或页码"
            />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {visiblePages.map(page => (
            <button
              key={page.page}
              type="button"
              onClick={() => setActivePage(page.page)}
              className={cn(
                'mb-1 w-full rounded-md px-3 py-2 text-left text-xs transition',
                selectedPage?.page === page.page
                  ? 'bg-slate-900 text-white'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              )}
            >
              <span className="font-mono">第 {page.page} 页</span>
              <span className={cn(
                'mt-1 block truncate',
                selectedPage?.page === page.page ? 'text-slate-300' : 'text-slate-400'
              )}>
                {page.text.replace(/\s+/g, ' ').slice(0, 48)}
              </span>
            </button>
          ))}
          {visiblePages.length === 0 && (
            <p className="px-3 py-6 text-center text-xs text-slate-400">没有匹配页面</p>
          )}
        </div>
      </aside>

      <main className="min-h-0 overflow-y-auto">
        <article className="mx-auto max-w-4xl p-6 pb-16">
          <header className="mb-4 flex flex-wrap items-start justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="min-w-0">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-slate-400">
                Source · Page {selectedPage?.page || 1} / {paper.page_count || paper.pages.length}
              </div>
              <h1 className="mt-1 truncate text-base font-semibold text-slate-900">{paper.title}</h1>
              <p className="mt-1 text-xs text-slate-500">
                {(paper.authors || []).slice(0, 4).join('、') || '作者未识别'}
                {paper.year ? ` · ${paper.year}` : ''}
              </p>
            </div>
            {sourceHref && (
              <a
                href={sourceHref}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 px-3 text-xs font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
              >
                打开原 PDF <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
          </header>
          {paper.text_truncated && (
            <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              当前仅解析了 {paper.page_count_parsed || paper.pages.length} / {paper.page_count_total || paper.page_count} 页；报告与追问不能覆盖未解析页面。
            </div>
          )}
          <section className="rounded-lg border border-slate-200 bg-white px-7 py-8 shadow-sm">
            <div className="mb-6 flex items-center justify-between border-b border-slate-100 pb-3">
              <span className="text-sm font-semibold text-slate-900">第 {selectedPage?.page || 1} 页</span>
              <span className="font-mono text-[10px] text-slate-400">
                {selectedPage?.text.length || 0} chars
              </span>
            </div>
            <p className="whitespace-pre-wrap break-words font-serif text-[15px] leading-8 text-slate-800">
              {selectedPage?.text || '本页没有可提取文字。'}
            </p>
          </section>
        </article>
      </main>
    </div>
  )
}
