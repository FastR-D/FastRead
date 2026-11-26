export type ReadingMode = 'skim' | 'deep' | 'repository'
export type RepositoryRequest = { url: string; commit: string; paths: string[] }
export type RepositorySnapshot = RepositoryRequest & {
  files: {
    path: string
    content: string
    line_start: number
    line_end: number
    truncated: boolean
  }[]
}
export type Implementation = ReadingItem & {
  code_evidence: { path: string; line_start: number; line_end: number; quote: string }[]
}
export type Evidence = {
  page?: number
  page_start?: number
  exact_quote?: string
  quote?: string
  version_id?: string
  paper_id?: string
}
export type ReadingItem = {
  question?: string
  answer?: string
  step?: string
  title?: string
  description?: string
  why_it_matters?: string
  input?: string
  output?: string
  purpose?: string
  evidence?: Evidence[]
  code_evidence?: { path: string; line_start: number; line_end: number; quote: string }[]
}
export type Expression = number | string | { op: string; args: Expression[] }
export type Formula = ReadingItem & {
  latex: string
  explanation: string
  variables?: { name: string; label: string; min: number; max: number; value: number }[]
  expression?: Expression
}
export type Experiment = {
  title: string
  conditions: string
  metric: string
  unit?: string
  rows: { label: string; value: string; evidence: Evidence[] }[]
}
export type ReadingContent = {
  repository_request?: RepositoryRequest
  repository?: RepositorySnapshot
  implementation?: Implementation[]
  executive_summary?: string
  reading_mode?: string
  key_questions?: ReadingItem[]
  process?: ReadingItem[]
  contributions?: ReadingItem[]
  limitations?: string[]
  terms?: { term: string; explanation: string }[]
  suggested_questions?: string[]
  formulas?: Formula[]
  experiments?: Experiment[]
  interaction_warnings?: string[]
}

// Interpret a bounded arithmetic tree; never eval model-authored strings or code.
export function evaluateExpression(
  expression: Expression,
  variables: Record<string, number>
): number {
  let budget = 128
  const visit = (node: Expression, depth: number): number => {
    if (--budget < 0 || depth > 16) throw new Error('公式过于复杂，仅支持分步解释。')
    let value: number
    if (typeof node === 'number') value = node
    else if (typeof node === 'string') {
      if (!Object.prototype.hasOwnProperty.call(variables, node))
        throw new Error('公式包含未定义变量。')
      value = variables[node]
    } else {
      if (!node || !Array.isArray(node.args)) throw new Error('公式结构不可计算。')
      const arity = ['neg', 'sqrt', 'exp', 'log'].includes(node.op)
        ? 1
        : ['add', 'sub', 'mul', 'div', 'pow'].includes(node.op)
          ? 2
          : 0
      if (!arity || node.args.length !== arity) throw new Error('此运算暂不支持。')
      const [a, b] = node.args.map(arg => visit(arg, depth + 1))
      switch (node.op) {
        case 'add':
          value = a + b
          break
        case 'sub':
          value = a - b
          break
        case 'mul':
          value = a * b
          break
        case 'div':
          value = a / b
          break
        case 'pow':
          value = a ** b
          break
        case 'neg':
          value = -a
          break
        case 'sqrt':
          value = Math.sqrt(a)
          break
        case 'exp':
          value = Math.exp(a)
          break
        case 'log':
          value = Math.log(a)
          break
        default:
          throw new Error('此运算暂不支持。')
      }
    }
    if (!Number.isFinite(value)) throw new Error('当前输入超出定义域或数值范围，请调整参数。')
    return value
  }
  return visit(expression, 0)
}

export function experimentDifference(value: string, baseline: string): number | null {
  if (!value.trim() || !baseline.trim()) return null
  const result = Number(value) - Number(baseline)
  return Number.isFinite(result) ? result : null
}

export function readingItemText(item: ReadingItem): string {
  const title = item.question || item.step || item.title || '阅读摘录'
  const citations = (item.evidence || [])
    .map(ev => `> 第 ${ev.page_start || ev.page} 页：${ev.exact_quote || ev.quote || ''}`)
    .join('\n\n')
  const code = (item.code_evidence || [])
    .map(
      ev =>
        `源码：${ev.path} · L${ev.line_start}–L${ev.line_end}\n\n${ev.quote
          .split('\n')
          .map(line => `    ${line}`)
          .join('\n')}`
    )
    .join('\n\n')
  return `### ${title}\n\n${item.answer || item.description || ''}\n\n${citations}${code ? `\n\n${code}` : ''}`
}

export function repositorySourceURL(
  repo: RepositoryRequest,
  file: string,
  start: number,
  end: number
): string | undefined {
  if (
    !/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo.url) ||
    !/^[a-f0-9]{40}$/i.test(repo.commit)
  )
    return undefined
  if (
    file.split('/').some(part => part === '..' || part === '.' || !part) ||
    !Number.isInteger(start) ||
    !Number.isInteger(end) ||
    start < 1 ||
    end < start
  )
    return undefined
  return `${repo.url}/blob/${repo.commit}/${file.split('/').map(encodeURIComponent).join('/')}#L${start}-L${end}`
}
