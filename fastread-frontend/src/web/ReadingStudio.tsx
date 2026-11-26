import { useEffect, useState } from 'react'
import {
  ActivityRail,
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  EmptyState,
  InspectorSection,
  PanelHeader,
  Progress,
  SegmentedControl,
  Section,
  Select,
  TextArea,
  TextField,
  Toolbar,
} from '@fastrd/ui-react'
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  Compass,
  Code2,
  Download,
  FlaskConical,
  GitBranch,
  Lightbulb,
  ListChecks,
  Sigma,
  Sparkles,
  StickyNote,
} from 'lucide-react'
import Markdown from './Markdown'
import { API_BASE } from './urls'
import {
  evaluateExpression,
  experimentDifference,
  readingItemText,
  repositorySourceURL,
  type ReadingMode,
  type RepositoryRequest,
  type Evidence,
  type Experiment,
  type Formula,
  type ReadingContent,
  type ReadingItem,
} from './readingModel'

type Report = { id: string; version_id: string; content: ReadingContent }
type Props = {
  paper: { id: string; title: string; active_version?: string }
  report: Report | null
  pending: boolean
  failure?: string
  canGenerate: boolean
  onGenerate: (mode: ReadingMode, repository?: RepositoryRequest) => Promise<void>
  onLocate: (evidence: Evidence) => void
  onAsk: (question: string, evidence?: Evidence) => void
  onSave: (text: string) => Promise<void>
}
const sections = [
  { id: 'overview', label: '论文速览', icon: Compass },
  { id: 'method', label: '方法拆解', icon: GitBranch },
  { id: 'formulas', label: '公式探索', icon: Sigma },
  { id: 'experiments', label: '实验对照', icon: FlaskConical },
  { id: 'implementation', label: '仓库联读', icon: Code2 },
  { id: 'review', label: '理解与追问', icon: ListChecks },
] as const

function EvidenceLinks({
  evidence = [],
  onLocate,
}: {
  evidence?: Evidence[]
  onLocate: Props['onLocate']
}) {
  return (
    <Toolbar label="原文依据" className="reading-evidence">
      {evidence.map((ev, i) => (
        <Button
          key={i}
          variant="quiet"
          size="xs"
          title={ev.exact_quote || ev.quote}
          onClick={() => onLocate(ev)}
        >
          <BookOpen size={13} /> 第 {ev.page_start || ev.page} 页 · 原文依据
        </Button>
      ))}
    </Toolbar>
  )
}

function FormulaLab({
  formula,
  onSave,
  onLocate,
}: {
  formula: Formula
  onSave: Props['onSave']
  onLocate: Props['onLocate']
}) {
  const defaults = Object.fromEntries((formula.variables || []).map(v => [v.name, v.value]))
  const [values, setValues] = useState(defaults)
  const [saving, setSaving] = useState(false)
  let result: number | undefined,
    error = ''
  if (formula.expression) {
    try {
      result = evaluateExpression(formula.expression, values)
    } catch (e) {
      error = (e as Error).message
    }
  }
  return (
    <Card className="formula-card">
      <CardBody>
        <PanelHeader>
          <h3>{formula.title}</h3>
          <Badge tone="info">{formula.expression ? '教学试算' : '公式解释'}</Badge>
        </PanelHeader>
        <Markdown math>{`$$\n${formula.latex}\n$$\n\n${formula.explanation}`}</Markdown>
        {formula.expression && (
          <>
            <p className="reading-muted">
              改变输入，观察公式输出。此计算用于理解公式，不代表论文实验或复现结果。
            </p>
            <div className="formula-variables">
              {formula.variables?.map(v => (
                <label className="fastui-field" key={v.name}>
                  {v.label || v.name}
                  <TextField
                    aria-label={`变量 ${v.name}`}
                    type="number"
                    min={v.min}
                    max={v.max}
                    step="any"
                    value={Number.isNaN(values[v.name]) ? '' : values[v.name]}
                    onChange={e =>
                      setValues({
                        ...values,
                        [v.name]:
                          e.target.value === ''
                            ? NaN
                            : Math.max(v.min, Math.min(v.max, Number(e.target.value))),
                      })
                    }
                  />
                  <small>
                    {v.min} ≤ {v.name} ≤ {v.max}
                  </small>
                </label>
              ))}
            </div>
            <output className="formula-output" aria-live="polite">
              {error ||
                `计算结果：${result?.toLocaleString('en-US', { maximumSignificantDigits: 8 })}`}
            </output>
            <Toolbar label="公式试算操作">
              <Button variant="quiet" onClick={() => setValues(defaults)}>
                重置输入
              </Button>
              <Button
                disabled={!!error || saving}
                loading={saving}
                onClick={async () => {
                  setSaving(true)
                  try {
                    await onSave(
                      `### 教学试算 · ${formula.title}\n\n输入：${JSON.stringify(values)}\n\n输出：${result}\n\n此记录为教学计算，不是论文实验结果。\n\n${(formula.evidence || []).map(ev => `> 第 ${ev.page_start || ev.page} 页：${ev.exact_quote || ev.quote}`).join('\n\n')}`
                    )
                  } finally {
                    setSaving(false)
                  }
                }}
              >
                保存试算到主笔记
              </Button>
            </Toolbar>
          </>
        )}
        <EvidenceLinks evidence={formula.evidence} onLocate={onLocate} />
      </CardBody>
    </Card>
  )
}

function ExperimentTable({
  experiment,
  onLocate,
}: {
  experiment: Experiment
  onLocate: Props['onLocate']
}) {
  const [baseline, setBaseline] = useState('0')
  const [order, setOrder] = useState('source')
  const rows = experiment.rows || []
  const shown = rows
    .map((row, index) => ({ ...row, index }))
    .sort((a, b) =>
      order === 'ascending'
        ? Number(a.value) - Number(b.value)
        : order === 'descending'
          ? Number(b.value) - Number(a.value)
          : a.index - b.index
    )
  return (
    <Card>
      <CardBody>
        <h3>{experiment.title}</h3>
        <p>{experiment.conditions}</p>
        <Toolbar label="实验比较设置">
          <label className="fastui-field">
            比较基准
            <Select
              aria-label="实验比较基准"
              value={baseline}
              onChange={e => setBaseline(e.target.value)}
            >
              {rows.map((row, i) => (
                <option key={i} value={i}>
                  {row.label}
                </option>
              ))}
            </Select>
          </label>
          <label className="fastui-field">
            排序
            <Select value={order} onChange={e => setOrder(e.target.value)}>
              <option value="source">论文顺序</option>
              <option value="ascending">数值升序</option>
              <option value="descending">数值降序</option>
            </Select>
          </label>
        </Toolbar>
        <div
          className="fastui-table-scroll"
          role="region"
          aria-label={experiment.title}
          tabIndex={0}
        >
          <table className="fastui-table">
            <thead>
              <tr>
                <th>方法 / 条件</th>
                <th>
                  {experiment.metric} {experiment.unit && `(${experiment.unit})`}
                </th>
                <th>与基准之差</th>
                <th>依据</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(row => {
                const difference = experimentDifference(
                  row.value,
                  rows[Number(baseline)]?.value || ''
                )
                return (
                  <tr key={row.index}>
                    <th scope="row">{row.label}</th>
                    <td>{row.value}</td>
                    <td>
                      {difference === null
                        ? '未报告'
                        : `${difference > 0 ? '+' : ''}${Number(difference.toPrecision(6))}`}
                    </td>
                    <td>
                      <EvidenceLinks evidence={row.evidence} onLocate={onLocate} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <small className="reading-muted">
          仅对照本表条件下的报告数值。差值不自动代表显著性或方法优劣。
        </small>
      </CardBody>
    </Card>
  )
}

export default function ReadingStudio({
  paper,
  report,
  pending,
  failure,
  canGenerate,
  onGenerate,
  onLocate,
  onAsk,
  onSave,
}: Props) {
  const contextKey = `reading-context:${paper.id}:${report?.id || 'new'}`
  const [section, setSection] = useState(() => {
    const stored = localStorage.getItem(contextKey)
    return sections.some(s => s.id === stored) ? stored! : 'overview'
  })
  useEffect(() => {
    localStorage.setItem(contextKey, section)
  }, [contextKey, section])
  const [mode, setMode] = useState<ReadingMode>(() =>
    ['skim', 'deep', 'repository'].includes(report?.content.reading_mode || '')
      ? (report!.content.reading_mode as ReadingMode)
      : 'deep'
  )
  const originalRepository = report?.content.repository || report?.content.repository_request
  const [repositoryUrl, setRepositoryUrl] = useState(originalRepository?.url || '')
  const [repositoryCommit, setRepositoryCommit] = useState(originalRepository?.commit || '')
  const [repositoryPaths, setRepositoryPaths] = useState(
    originalRepository?.paths.join('\n') || 'README.md'
  )
  const repositoryValid =
    /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repositoryUrl) &&
    /^[a-f0-9]{40}$/i.test(repositoryCommit) &&
    !!repositoryPaths.trim() &&
    repositoryPaths.trim().split(/\n/).length <= 6
  const [starting, setStarting] = useState(false)
  const [step, setStep] = useState(0)
  const [guided, setGuided] = useState(false)
  const [revealed, setRevealed] = useState<Record<number, boolean>>({})
  const [saved, setSaved] = useState('')
  const [saveError, setSaveError] = useState('')
  const progressKey = `reading-visited:${paper.id}:${report?.id || 'new'}`
  const [visited, setVisited] = useState<string[]>(() => {
    try {
      const value = JSON.parse(localStorage.getItem(progressKey) || '[]')
      return Array.isArray(value)
        ? [...new Set<string>(value.filter(id => sections.some(s => s.id === id)))]
        : []
    } catch {
      return []
    }
  })
  const [answers, setAnswers] = useState<Record<number, string>>(() => {
    try {
      const value = JSON.parse(
        localStorage.getItem(`reading-recall:${paper.id}:${report?.id}`) || '{}'
      )
      return value && typeof value === 'object' && !Array.isArray(value)
        ? Object.fromEntries(
            Object.entries(value).filter(
              (entry): entry is [string, string] =>
                /^\d+$/.test(entry[0]) && typeof entry[1] === 'string'
            )
          )
        : {}
    } catch {
      return {}
    }
  })
  const content = report?.content || {}
  const methods = content.process || [],
    current = methods[Math.min(step, Math.max(0, methods.length - 1))]
  const locate = (ev: Evidence) => onLocate({ ...ev, version_id: report?.version_id })
  async function save(text: string) {
    setSaveError('')
    setSaved('')
    try {
      await onSave(
        `${text}\n\n来源文档版本：${report?.version_id || '未知'}${content.repository ? `\n仓库：${content.repository.url} · ${content.repository.commit}` : ''}`
      )
      setSaved('已追加到主笔记')
    } catch (e) {
      setSaveError((e as Error).message)
    }
  }
  const actions = (item: ReadingItem) => (
    <Toolbar label="阅读内容操作">
      <Button
        variant="quiet"
        onClick={() =>
          onAsk(
            `请进一步解释：${item.question || item.step || item.title}\n\n${item.answer || item.description || ''}${item.code_evidence?.length ? `\n以下为固定提交的源码摘录（仅以这些片段讨论实现，不声称执行代码）：\n${item.code_evidence.map(ev => `${ev.path} L${ev.line_start}–L${ev.line_end}\n${ev.quote}`).join('\n')}` : ''}`,
            item.evidence?.[0] ? { ...item.evidence[0], version_id: report?.version_id } : undefined
          )
        }
      >
        <Sparkles size={14} /> 继续追问
      </Button>
      <Button variant="quiet" onClick={() => void save(readingItemText(item))}>
        <StickyNote size={14} /> 摘录到主笔记
      </Button>
      <EvidenceLinks evidence={item.evidence} onLocate={locate} />
    </Toolbar>
  )
  return (
    <Section className="reading-studio">
      <Section role="complementary" className="reading-outline" aria-label="阅读路线">
        <h2>本篇导览</h2>
        <ActivityRail label="阅读章节">
          {sections.map(({ id, label, icon: Icon }, i) => (
            <Button
              key={id}
              variant="navigation"
              aria-current={section === id ? 'step' : undefined}
              onClick={() => setSection(id)}
            >
              <Icon size={16} />
              <span>{label}</span>
              <small>{visited.includes(id) ? <Check size={13} /> : `0${i + 1}`}</small>
            </Button>
          ))}
        </ActivityRail>
        <div className="reading-route-progress">
          <Progress label="已浏览环节" value={visited.length} max={sections.length} />
          <small>
            {visited.length} / {sections.length} 个环节已浏览
          </small>
        </div>
        {report && (
          <a
            className="fastui-link reading-export"
            href={`${API_BASE}/papers/${paper.id}/export?report=${encodeURIComponent(report.id)}`}
            download
          >
            <Download size={14} /> 导出本次阅读
          </a>
        )}
      </Section>
      <Section className="reading-article" role="region" aria-label="交互阅读内容" tabIndex={0}>
        <PanelHeader className="reading-article-header">
          <div>
            <span className="reading-eyebrow">
              {content.reading_mode === 'skim' ? '泛读' : '精读'} /{' '}
              {sections.find(s => s.id === section)?.label}
            </span>
            <h1>{paper.title}</h1>
          </div>
        </PanelHeader>
        {saved && <Alert tone="success">{saved}</Alert>}
        {saveError && <Alert tone="danger">{saveError}</Alert>}
        <InspectorSection
          className="reading-generation"
          label={report ? '生成新的阅读' : '选择阅读方式'}
          open={!report || undefined}
        >
          <div className="reading-launcher">
            <div className="reading-launcher-actions">
              <SegmentedControl
                label="阅读深度"
                value={mode}
                onChange={v => setMode(v as ReadingMode)}
                options={[
                  { value: 'skim', label: '快速泛读' },
                  { value: 'deep', label: '完整精读' },
                  { value: 'repository', label: '关联仓库精读' },
                ]}
              />
              <Button
                variant="primary"
                loading={pending || starting}
                disabled={
                  !canGenerate || pending || starting || (mode === 'repository' && !repositoryValid)
                }
                onClick={async () => {
                  setStarting(true)
                  try {
                    await onGenerate(
                      mode,
                      mode === 'repository'
                        ? {
                            url: repositoryUrl,
                            commit: repositoryCommit,
                            paths: repositoryPaths
                              .split('\n')
                              .map(p => p.trim())
                              .filter(Boolean),
                          }
                        : undefined
                    )
                  } finally {
                    setStarting(false)
                  }
                }}
              >
                <Sparkles size={14} />
                {pending ? '正在生成阅读内容' : report ? '生成新的阅读' : '开始阅读'}
              </Button>
            </div>
          </div>
          {mode === 'repository' && (
            <div className="repository-config">
              <label className="fastui-field">
                公开 GitHub 仓库
                <TextField
                  aria-label="联读仓库地址"
                  value={repositoryUrl}
                  onChange={e => setRepositoryUrl(e.target.value)}
                  placeholder="https://github.com/owner/repository"
                  type="url"
                />
              </label>
              <label className="fastui-field">
                固定提交
                <TextField
                  aria-label="联读提交 SHA"
                  value={repositoryCommit}
                  onChange={e => setRepositoryCommit(e.target.value)}
                  placeholder="40 位 commit SHA"
                  maxLength={40}
                />
              </label>
              <label className="fastui-field">
                要阅读的文件
                <TextArea
                  aria-label="联读文件路径"
                  value={repositoryPaths}
                  onChange={e => setRepositoryPaths(e.target.value)}
                  placeholder="每行一个相对路径，最多 6 个"
                  rows={3}
                />
              </label>
              <p className="reading-muted">
                读取固定提交中指定的公开源码片段，并与论文一起发送给当前模型；不执行代码。每个文件最多读取前
                300 行 / 12 KB，阅读结果会注明覆盖范围。
              </p>
            </div>
          )}
        </InspectorSection>
        {!canGenerate && <Alert tone="info">请先在设置中选择可用模型，并确认论文已有 PDF。</Alert>}
        {failure && !pending && (
          <Alert tone="danger">{failure} · 可以重新生成，已有阅读记录仍保留。</Alert>
        )}
        {pending && <Progress label="阅读内容生成中" />}
        {!report ? (
          <EmptyState title="暂无阅读记录">
            <p>
              选择泛读或精读，生成论文速览、方法拆解与带原文依据的解释。也可以直接切换到原文阅读。
            </p>
          </EmptyState>
        ) : (
          <>
            {section === 'overview' && (
              <Section className="reading-section">
                <Card variant="secondary" className="reading-lead">
                  <Lightbulb size={20} />
                  <div>
                    <h2>这篇论文在解决什么？</h2>
                    <Markdown math>
                      {content.executive_summary ||
                        '此历史报告没有独立总览，请从关键问题开始阅读。'}
                    </Markdown>
                  </div>
                </Card>
                <h2>关键问题</h2>
                {(content.key_questions || []).map((item, i) => (
                  <Card key={i}>
                    <CardBody>
                      <span className="reading-question-number">
                        问题 {String(i + 1).padStart(2, '0')}
                      </span>
                      <h3>{item.question}</h3>
                      <Markdown math>{item.answer || ''}</Markdown>
                      {item.why_it_matters && (
                        <p className="reading-muted">为什么重要：{item.why_it_matters}</p>
                      )}
                      {actions(item)}
                    </CardBody>
                  </Card>
                ))}
                {!!content.contributions?.length && (
                  <>
                    <h2>贡献与边界</h2>
                    {content.contributions.map((item, i) => (
                      <Card key={i}>
                        <CardBody>
                          <h3>{item.title}</h3>
                          <Markdown math>{item.description || ''}</Markdown>
                          {actions(item)}
                        </CardBody>
                      </Card>
                    ))}
                  </>
                )}
                {!!content.limitations?.length && (
                  <Alert tone="warning">
                    <strong>阅读时保留这些边界</strong>
                    <ul>
                      {content.limitations.map((text, i) => (
                        <li key={i}>{text}</li>
                      ))}
                    </ul>
                  </Alert>
                )}
                {!!content.terms?.length && (
                  <InspectorSection label="术语速查">
                    {content.terms.map((term, i) => (
                      <div key={i}>
                        <strong>{term.term}</strong>
                        <p>{term.explanation}</p>
                      </div>
                    ))}
                  </InspectorSection>
                )}
              </Section>
            )}
            {section === 'method' && (
              <Section className="reading-section">
                <h2>沿着方法走一遍</h2>
                <p className="reading-muted">
                  按论文报告的顺序检查每一步。步骤顺序不额外推断模块间依赖。
                </p>
                {methods.length ? (
                  <>
                    <ActivityRail label="方法步骤" className="method-path">
                      {methods.map((item, i) => (
                        <Button
                          key={i}
                          variant="navigation"
                          aria-pressed={step === i}
                          onClick={() => setStep(i)}
                        >
                          <span className="method-number">{i + 1}</span>
                          {item.step}
                        </Button>
                      ))}
                    </ActivityRail>
                    <Card>
                      <CardBody>
                        <PanelHeader>
                          <h3>{current.step}</h3>
                          <Badge tone="info">
                            {step + 1} / {methods.length}
                          </Badge>
                        </PanelHeader>
                        <Markdown math>{current.description || ''}</Markdown>
                        <dl className="method-io">
                          {[
                            ['输入', current.input],
                            ['输出', current.output],
                            ['设计理由', current.purpose],
                          ].map(([label, value]) => (
                            <div key={label}>
                              <dt>{label}</dt>
                              <dd>{value || '当前记录未提供，可继续追问或回到原文。'}</dd>
                            </div>
                          ))}
                        </dl>
                        {actions(current)}
                      </CardBody>
                    </Card>
                    <Toolbar label="方法步进">
                      <Button disabled={step === 0} onClick={() => setStep(step - 1)}>
                        <ArrowLeft size={14} /> 上一步
                      </Button>
                      <Button
                        disabled={step >= methods.length - 1}
                        onClick={() => setStep(step + 1)}
                      >
                        下一步 <ArrowRight size={14} />
                      </Button>
                    </Toolbar>
                  </>
                ) : (
                  <EmptyState title="此记录没有方法步骤">
                    可重新生成完整精读，或回到原文核对。
                  </EmptyState>
                )}
              </Section>
            )}
            {section === 'formulas' && (
              <Section className="reading-section">
                <h2>理解符号，也理解变化</h2>
                {content.formulas?.length ? (
                  content.formulas.map((formula, i) => (
                    <FormulaLab key={i} formula={formula} onSave={save} onLocate={locate} />
                  ))
                ) : (
                  <EmptyState title="暂无可核对的公式材料">
                    历史报告或原文不足时不生成试算。可以生成新的完整精读，或选中原文公式继续追问。
                  </EmptyState>
                )}
              </Section>
            )}
            {section === 'experiments' && (
              <Section className="reading-section">
                <h2>在相同条件下比较</h2>
                {content.experiments?.length ? (
                  content.experiments.map((experiment, i) => (
                    <ExperimentTable key={i} experiment={experiment} onLocate={locate} />
                  ))
                ) : (
                  <EmptyState title="暂无可核对的实验表">
                    仅展示数值能在原文引文中匹配的数据。缺失数据不会填为零。
                  </EmptyState>
                )}
              </Section>
            )}
            {section === 'implementation' && (
              <Section className="reading-section">
                <h2>从论文到实现</h2>
                {content.repository ? (
                  <>
                    <Alert tone="info">
                      <strong>固定提交 · {content.repository.commit.slice(0, 12)}</strong>
                      <p>{content.repository.url}</p>
                      <p>仅解释已读取的源码片段，未执行代码或复现实验。</p>
                    </Alert>
                    {content.implementation?.length ? (
                      content.implementation.map((item, i) => (
                        <Card key={i}>
                          <CardBody>
                            <h3>{item.title}</h3>
                            <Markdown math>{item.description || ''}</Markdown>
                            {actions(item)}
                            {item.code_evidence.map((ev, j) => (
                              <div className="repository-evidence" key={j}>
                                <a
                                  className="fastui-link"
                                  href={repositorySourceURL(
                                    content.repository!,
                                    ev.path,
                                    ev.line_start,
                                    ev.line_end
                                  )}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  {ev.path} · L{ev.line_start}–L{ev.line_end}
                                </a>
                                <pre>
                                  <code>{ev.quote}</code>
                                </pre>
                              </div>
                            ))}
                          </CardBody>
                        </Card>
                      ))
                    ) : (
                      <EmptyState title="尚无可同时核对的论文与代码对应">
                        已保留源码快照；模型未提供同时通过页码与源码行核对的实现解释。
                      </EmptyState>
                    )}
                    <InspectorSection label="已读取的源码快照与范围">
                      {content.repository.files.map(file => (
                        <InspectorSection
                          key={file.path}
                          label={`${file.path} · L${file.line_start}–L${file.line_end}${file.truncated ? ' · 已截断' : ''}`}
                        >
                          <pre className="repository-source">
                            <code>{file.content}</code>
                          </pre>
                        </InspectorSection>
                      ))}
                    </InspectorSection>
                  </>
                ) : (
                  <EmptyState title="连接论文与真实实现">
                    选择「关联仓库精读」，填写公开仓库、固定提交和要阅读的文件。源码证据会保留路径、行号与逐字片段。
                  </EmptyState>
                )}
              </Section>
            )}
            {section === 'review' && (
              <Section className="reading-section">
                <PanelHeader>
                  <h2>用自己的话解释</h2>
                  <Button aria-pressed={guided} onClick={() => setGuided(!guided)}>
                    {guided ? '退出自测' : '开始引导自测'}
                  </Button>
                </PanelHeader>
                <p className="reading-muted">
                  先写理解，再查看解释。草稿保存在本机；需要模型反馈时，发送到对话继续讨论。
                </p>
                {(content.key_questions || []).map((item, i) => (
                  <Card key={i}>
                    <CardBody>
                      <h3>{item.question}</h3>
                      <TextArea
                        aria-label={`我的理解 ${i + 1}`}
                        rows={3}
                        maxLength={5000}
                        value={answers[i] || ''}
                        placeholder="先试着用自己的话解释…"
                        onChange={e => {
                          const next = { ...answers, [i]: e.target.value }
                          setAnswers(next)
                          localStorage.setItem(
                            `reading-recall:${paper.id}:${report.id}`,
                            JSON.stringify(next)
                          )
                        }}
                      />
                      {(!guided || revealed[i]) && <Markdown math>{item.answer || ''}</Markdown>}
                      <Toolbar label="理解自测操作">
                        {guided && (
                          <Button
                            variant="quiet"
                            onClick={() => setRevealed({ ...revealed, [i]: !revealed[i] })}
                          >
                            {revealed[i] ? '收起解释' : '查看解释'}
                          </Button>
                        )}
                        <Button
                          disabled={!answers[i]?.trim()}
                          onClick={() =>
                            onAsk(
                              `请依据原文检查我的理解，指出遗漏或错误，不要仅凭阅读进度判断掌握程度。\n问题：${item.question}\n我的理解：${answers[i]}`,
                              item.evidence?.[0]
                                ? { ...item.evidence[0], version_id: report.version_id }
                                : undefined
                            )
                          }
                        >
                          请 AI 反馈
                        </Button>
                        <Button
                          disabled={!answers[i]?.trim()}
                          variant="quiet"
                          onClick={() =>
                            void save(`### 我的理解 · ${item.question}\n\n${answers[i]}`)
                          }
                        >
                          保存理解到主笔记
                        </Button>
                      </Toolbar>
                      <EvidenceLinks evidence={item.evidence} onLocate={locate} />
                    </CardBody>
                  </Card>
                ))}
                {content.suggested_questions?.map((q, i) => (
                  <Button
                    key={i}
                    className="reading-question"
                    variant="quiet"
                    onClick={() => onAsk(q)}
                  >
                    <Sparkles size={14} />
                    {q}
                    <ArrowRight size={14} />
                  </Button>
                ))}
              </Section>
            )}
            {!!content.interaction_warnings?.length && (
              <InspectorSection label="未完成的材料">
                {content.interaction_warnings.map((warning, i) => (
                  <p key={i}>{warning}</p>
                ))}
              </InspectorSection>
            )}
            <footer className="reading-next">
              <Button
                variant="quiet"
                onClick={() => {
                  const next = [...new Set([...visited, section])]
                  setVisited(next)
                  localStorage.setItem(progressKey, JSON.stringify(next))
                  const index = sections.findIndex(s => s.id === section)
                  if (index < sections.length - 1) setSection(sections[index + 1].id)
                }}
              >
                <Check size={14} />
                {section === 'review' ? '记录本环节已浏览' : '记录已浏览，继续下一环节'}
                <ArrowRight size={14} />
              </Button>
            </footer>
          </>
        )}
      </Section>
    </Section>
  )
}
