import { useState } from 'react'
import { ArrowUpRight, ChevronDown, Upload } from 'lucide-react'
import Modal from './Modal'
import type { Row } from './api'

export default function ImportDialog({
  target,
  books,
  providers,
  submit,
  onClose,
  onComplete,
}: {
  target: Row
  books: Row[]
  providers: Row[]
  submit: (path: string, body?: unknown) => Promise<unknown>
  onClose: () => void
  onComplete: () => void
}) {
  const [kind, setKind] = useState(target.url && !target.paperId ? 'url' : 'file')
  const [file, setFile] = useState<File | null>(null)
  const [url, setUrl] = useState(target.url || '')
  const [book, setBook] = useState(target.bookId || '')
  const [model, setModel] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  function chooseFile(value?: File) {
    if (!value) return
    if (!/\.pdf$/i.test(value.name)) {
      setError('请选择 PDF 文件。')
      return
    }
    setFile(value)
    setError('')
  }
  async function send() {
    setBusy(true)
    setError('')
    try {
      const [provider_id, modelName] = model.split('|')
      if (kind === 'file') {
        if (!file) throw new Error('请先选择 PDF 文件。')
        const data = new FormData()
        data.set('file', file)
        data.set('knowledge_id', book)
        if (target.paperId) data.set('paper_id', target.paperId)
        if (provider_id) {
          data.set('provider_id', provider_id)
          data.set('model', modelName)
        }
        await submit('/imports/pdf', data)
      } else
        await submit('/imports/url', {
          url,
          knowledge_id: book,
          ...(provider_id ? { provider_id, model: modelName } : {}),
        })
      onComplete()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal
      title={target.paperId ? '补充论文 PDF' : '导入论文'}
      description={
        target.paperId
          ? '上传原文件，补全这条已有资料。'
          : '加入文献库后，可以阅读原文、批注和提问。'
      }
      onClose={() => {
        if (!busy) onClose()
      }}
    >
      {!target.paperId && (
        <div className="segmented-control" role="group" aria-label="导入方式">
          <button
            aria-pressed={kind === 'file'}
            className={kind === 'file' ? 'active' : ''}
            onClick={() => setKind('file')}
          >
            上传 PDF
          </button>
          <button
            aria-pressed={kind === 'url'}
            className={kind === 'url' ? 'active' : ''}
            onClick={() => setKind('url')}
          >
            粘贴链接
          </button>
        </div>
      )}
      <form
        onSubmit={e => {
          e.preventDefault()
          void send()
        }}
      >
        {kind === 'file' ? (
          <label
            className="upload-zone"
            onDragOver={e => e.preventDefault()}
            onDrop={e => {
              e.preventDefault()
              if (!busy) chooseFile(e.dataTransfer.files[0])
            }}
          >
            <Upload size={26} />
            <strong>{file?.name || '选择或拖入 PDF'}</strong>
            <span>
              {file
                ? `${(file.size / 1024 / 1024).toFixed(1)} MB · 点击更换文件`
                : '原文件和批注会保存在资料库'}
            </span>
            <input
              type="file"
              accept="application/pdf,.pdf"
              aria-label="选择 PDF 文件"
              disabled={busy}
              onChange={e => chooseFile(e.target.files?.[0])}
            />
          </label>
        ) : (
          <label>
            论文链接
            <input
              type="url"
              aria-label="论文链接"
              required
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://arxiv.org/abs/…"
            />
          </label>
        )}
        <label>
          加入知识库
          <select value={book} onChange={e => setBook(e.target.value)}>
            <option value="">自动归类</option>
            {books.map(b => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </label>
        <details className="advanced-options">
          <summary>
            高级选项 <ChevronDown size={13} />
          </summary>
          <label>
            标题与作者识别
            <select value={model} onChange={e => setModel(e.target.value)}>
              <option value="">使用版面与公开索引</option>
              {providers.flatMap(p =>
                p.models.map((m: string) => (
                  <option key={`${p.id}|${m}`} value={`${p.id}|${m}`}>
                    {m} · {p.name}
                  </option>
                ))
              )}
            </select>
          </label>
          {model && <small>所选模型会读取第一页文本，占用模型任务额度。</small>}
        </details>
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="dialog-footer">
          <button type="button" className="quiet" disabled={busy} onClick={onClose}>
            取消
          </button>
          <button disabled={busy || (kind === 'file' && !file)}>
            {busy ? '提交中…' : '开始导入'}
            <ArrowUpRight size={15} />
          </button>
        </div>
      </form>
    </Modal>
  )
}
