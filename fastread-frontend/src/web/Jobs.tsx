import { useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  EmptyState,
  InspectorSection,
  Section,
  Select,
  TextField,
} from '@fastrd/ui-react'
import { RefreshCw } from 'lucide-react'
import type { Job } from './Organize'
import { ListFooter, ListTable, PageHeading, pageSize } from './ListPage'

const kinds: Record<string, string> = {
  import_pdf: '导入 PDF',
  import_url: '链接导入',
  index: '构建索引',
  organize: '整理论文',
  report: '生成阅读报告',
  chat: '论文对话',
  knowledge_chat: '知识库对话',
  book_questions: '生成研究问题',
  neighbors: '查找近邻论文',
  research_directions: '生成研究方向',
}
const states = {
  queued: { label: '排队中', tone: 'info' },
  running: { label: '处理中', tone: 'info' },
  succeeded: { label: '已完成', tone: 'success' },
  failed: { label: '失败', tone: 'danger' },
  needs_attention: { label: '需要处理', tone: 'warning' },
  cancelled: { label: '已取消', tone: 'info' },
} as const
function timestamp(value?: number) {
  return value ? new Date(value * 1000).toLocaleString('zh-CN', { hour12: false }) : '—'
}
export default function Jobs({ jobs, onRefresh }: { jobs: Job[]; onRefresh: () => Promise<void> }) {
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState('')
  const [state, setState] = useState('')
  const [page, setPage] = useState(1)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const needle = query.trim().toLowerCase()
  const filtered = jobs.filter(
    job =>
      (!kind || job.kind === kind) &&
      (!state || job.state === state) &&
      `${job.id} ${job.kind} ${kinds[job.kind] || ''} ${job.error || ''}`
        .toLowerCase()
        .includes(needle)
  )
  const currentPage = Math.min(page, Math.max(1, Math.ceil(filtered.length / pageSize)))
  return (
    <Section className="jobs-page app-page" aria-label="后台任务">
      <PageHeading title="后台任务">
        <span className="jobs-scope">最近 {jobs.length} 条任务</span>
      </PageHeading>
      <div className="flex flex-wrap items-center gap-3">
        <TextField
          type="search"
          className="w-full sm:max-w-sm"
          aria-label="搜索任务"
          placeholder="搜索任务类型、编号或错误信息"
          value={query}
          onChange={e => {
            setQuery(e.target.value)
            setPage(1)
          }}
        />
        <Select
          aria-label="筛选任务类型"
          value={kind}
          onChange={e => {
            setKind(e.target.value)
            setPage(1)
          }}
        >
          <option value="">全部类型</option>
          {Array.from(new Set([...Object.keys(kinds), ...jobs.map(job => job.kind)])).map(key => (
            <option key={key} value={key}>
              {kinds[key] || key}
            </option>
          ))}
        </Select>
        <Select
          aria-label="筛选任务状态"
          value={state}
          onChange={e => {
            setState(e.target.value)
            setPage(1)
          }}
        >
          <option value="">全部状态</option>
          {Object.entries(states).map(([key, value]) => (
            <option key={key} value={key}>
              {value.label}
            </option>
          ))}
        </Select>
        <Button
          variant="quiet"
          className="sm:ml-auto"
          loading={refreshing}
          onClick={async () => {
            setRefreshing(true)
            setError('')
            try {
              await onRefresh()
            } catch (e) {
              setError((e as Error).message)
            } finally {
              setRefreshing(false)
            }
          }}
        >
          <RefreshCw size={15} />
          刷新
        </Button>
      </div>
      {error && <Alert tone="danger">{error}</Alert>}
      <ListTable
        label="后台任务列表"
        columns={['任务', '状态', '创建时间', '更新时间', '详情']}
        rows={filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize).map(job => {
          const status = states[job.state as keyof typeof states]
          return {
            id: job.id,
            cells: [
              <div className="job-identity">
                <strong>{kinds[job.kind] || job.kind}</strong>
                <span title={job.id}>{job.id}</span>
              </div>,
              <Badge tone={status?.tone || 'info'}>{status?.label || job.state}</Badge>,
              <span className="job-time">{timestamp(job.created)}</span>,
              <span className="job-time">{timestamp(job.updated)}</span>,
              job.error ? (
                <InspectorSection className="job-error-details" label="查看错误">
                  <p>{job.error}</p>
                </InspectorSection>
              ) : (
                <span className="jobs-muted">—</span>
              ),
            ],
          }
        })}
      />
      {!filtered.length && (
        <EmptyState title={query || kind || state ? '没有匹配的任务' : '暂无任务'} />
      )}
      <ListFooter count={filtered.length} page={currentPage} onPage={setPage} unit="条任务" />
    </Section>
  )
}
