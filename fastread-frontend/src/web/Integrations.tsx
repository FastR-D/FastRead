import { useEffect, useState } from 'react'
import { Alert, Badge, Button, Select, TextArea, TextField } from '@fastrd/ui-react'
import { Download, Newspaper, PenLine } from 'lucide-react'
import { AppDialog } from './Chrome'

type Row = Record<string, any>
type Api = (path: string, method?: string, body?: unknown, key?: string) => Promise<any>

export function IntegrationStatus({ api }: { api: Api }) {
  const [status, setStatus] = useState<Row | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  useEffect(() => { void api('/integrations/status').then(setStatus).catch(e => setError(e.message)) }, [api])
  async function connect(service: string, token?: string) {
    setBusy(service); setError('')
    try { await api(`/integrations/connections/${service}`, token ? 'POST' : 'DELETE', token ? { token } : undefined); setStatus(await api('/integrations/status')) } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  return <section className="integration-status"><h2>应用联动</h2>{error && <Alert tone="danger">{error}</Alert>}{status ? ['fastwrite', 'fastnews'].map(key => <section className="integration-connection" key={key}><div className="section-heading"><strong>{key === 'fastwrite' ? 'FastWrite 写作' : 'FastNews 科研动态'}</strong><Badge tone={status[key]?.connected ? 'success' : 'warning'}>{status[key]?.connected ? '已连接' : '待连接'}</Badge></div>{status[key]?.connected ? <Button variant="quiet" disabled={!!busy} onClick={() => void connect(key)}>断开连接</Button> : <form onSubmit={e => { e.preventDefault(); const form = e.currentTarget; const token = String(new FormData(form).get('token')).trim(); void connect(key, token).then(() => form.reset()) }}><p>在 {key === 'fastwrite' ? 'FastWrite 研究面板' : 'FastNews 账户页'} 生成 FastRead 连接码，然后粘贴到这里。{status[key]?.url && <a href={status[key].url} target="_blank" rel="noreferrer">打开应用</a>}</p><label>连接码<TextField name="token" type="password" autoComplete="off" required /></label><Button type="submit" loading={busy === key} disabled={!!busy}>保存连接</Button></form>}</section>) : !error && <p role="status">正在读取联动状态…</p>}<p>在论文库勾选论文后，可交接写作素材，或提炼研究方向同步至 FastNews。</p></section>
}

export default function IntegrationActions({ api, paperIds, providerId, model }: { api: Api; paperIds: string[]; providerId: string; model: string }) {
  const [dialog, setDialog] = useState<'news' | 'write' | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [projects, setProjects] = useState<Row[]>([])
  const [projectId, setProjectId] = useState('')
  const [question, setQuestion] = useState('')
  const [text, setText] = useState('')
  const [current, setCurrent] = useState('')
  const [mode, setMode] = useState('append')
  const [jobId, setJobId] = useState('')
  const [format, setFormat] = useState('markdown')
  const [syncedUrl, setSyncedUrl] = useState('')
  const directionsTooLong = text.trim().length > 4000 || (mode === 'append' && current.length + text.trim().length + (current ? 2 : 0) > 4000)
  useEffect(() => {
    if (!dialog) return
    setError(''); setNotice(''); setSyncedUrl('')
    if (dialog === 'write') void api('/integrations/fastwrite/projects').then(data => setProjects(data.items)).catch(e => setError(e.message))
    else void api('/integrations/fastnews/directions').then(data => setCurrent(data.text || data.impression || '')).catch(e => setError(e.message))
  }, [api, dialog])
  useEffect(() => {
    if (!jobId) return
    let stopped = false
    const poll = async () => {
      try {
        const job = await api(`/jobs/${jobId}`)
        if (stopped) return
        if (job.state === 'succeeded') { setText(job.result.text || job.result.markdown || ''); setNotice('研究方向已提炼，可编辑后同步。'); setJobId('') }
        else if (['failed', 'needs_attention', 'cancelled'].includes(job.state)) { setError(job.error || '方向提炼未完成，请重试。'); setJobId('') }
      } catch (e) { if (!stopped) { setError((e as Error).message); setJobId('') } }
    }
    void poll(); const timer = setInterval(poll, 3000)
    return () => { stopped = true; clearInterval(timer) }
  }, [api, jobId])
  async function act(operation: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('')
    try { await operation() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  async function downloadBundle() {
    const result = await api('/integrations/fastwrite/export', 'POST', { paper_ids: paperIds })
    const suffix = format === 'bibtex' ? '/references.bib' : '/evidence.md'
    const content = format === 'json' ? JSON.stringify(result, null, 2) : result.files.find((file: Row) => file.path.endsWith(suffix))?.content
    if (!content) throw new Error('所选论文尚无可导出的资料。')
    const url = URL.createObjectURL(new Blob([content], { type: 'text/plain;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url; anchor.download = `fastread-papers.${format === 'markdown' ? 'md' : format === 'bibtex' ? 'bib' : 'json'}`
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    setNotice('论文资料已导出。')
  }
  return <>
    <Button variant="quiet" disabled={!paperIds.length} onClick={() => setDialog('write')}><PenLine size={15} /> 交接 FastWrite</Button>
    <Button variant="quiet" disabled={!paperIds.length} onClick={() => setDialog('news')}><Newspaper size={15} /> 提炼研究方向</Button>
    <AppDialog open={dialog !== null} onClose={() => setDialog(null)} title={dialog === 'write' ? '交接 FastWrite' : '提炼研究方向'}>
      <div className="research-dialog"><p>已选 {paperIds.length} 篇论文</p>{error && <Alert tone="danger">{error}</Alert>}{notice && <Alert tone="success">{notice}</Alert>}
        {dialog === 'write' ? <>
          <label>FastWrite 项目<Select value={projectId} onChange={e => setProjectId(e.target.value)}><option value="">选择写作项目</option>{projects.map(project => <option value={project.id} key={project.id}>{project.name}</option>)}</Select></label>
          <p>将论文元数据、阅读笔记和原文证据交接到所选写作项目。</p>
          <Button disabled={!projectId || busy} loading={busy} onClick={() => void act(async () => { const result = await api('/integrations/fastwrite/sync', 'POST', { project_id: projectId, paper_ids: paperIds }); setNotice('论文资料已同步到 FastWrite。'); setSyncedUrl(result.url || '') })}>同步到写作项目</Button>
          <Button variant="secondary" disabled={!projectId || busy} onClick={() => void act(async () => { const result = await api(`/integrations/fastwrite/projects/${encodeURIComponent(projectId)}/feedback`, 'POST'); setNotice(`已取回 ${result.saved} 条写作笔记，打开对应论文即可查看。`) })}>取回写作笔记</Button>
          {syncedUrl && <a href={syncedUrl} target="_blank" rel="noreferrer">打开 FastWrite 项目</a>}
          <label>下载格式<Select value={format} onChange={e => setFormat(e.target.value)}><option value="markdown">Markdown</option><option value="bibtex">BibTeX</option><option value="json">JSON 证据包</option></Select></label>
          <Button variant="secondary" disabled={busy} onClick={() => void act(downloadBundle)}><Download size={15} /> 下载资料</Button>
        </> : <>
          <label>关注的问题<TextField value={question} onChange={e => setQuestion(e.target.value)} placeholder="例如：轻量视觉模型的研究机会" maxLength={2000} /></label>
          <Button disabled={!providerId || busy || !!jobId} loading={!!jobId} onClick={() => void act(async () => { const result = await api('/research/directions', 'POST', { paper_ids: paperIds, provider_id: providerId, model, question }, crypto.randomUUID()); setJobId((result.job || result).id) })}>{jobId ? '正在提炼研究方向…' : '从所选论文提炼方向'}</Button>
          {!providerId && <p>请在设置中选择可用模型。</p>}
          <label>研究方向<TextArea aria-label="研究方向" value={text} onChange={e => setText(e.target.value)} rows={9} placeholder="生成后可在这里修改，也可以直接填写希望 FastNews 跟踪的方向。" maxLength={4000} /></label>
          <details><summary>FastNews 当前方向</summary><div className="integration-current">{current || '尚未设置研究方向'}</div></details>
          <label>同步方式<Select value={mode} onChange={e => setMode(e.target.value)}><option value="append">追加到当前方向</option><option value="replace">替换当前方向</option></Select></label>
          {directionsTooLong && <Alert tone="warning">FastNews 研究方向最多 4000 字，请精简内容或改为替换当前方向。</Alert>}
          <Button disabled={!text.trim() || directionsTooLong || busy || !!jobId} loading={busy} onClick={() => void act(async () => { await api('/integrations/fastnews/directions', 'POST', { text: text.trim(), mode }); const value = await api('/integrations/fastnews/directions'); setCurrent(value.text || value.impression || ''); setNotice('研究方向已同步到 FastNews。') })}>同步到 FastNews</Button>
        </>}
      </div>
    </AppDialog>
  </>
}
