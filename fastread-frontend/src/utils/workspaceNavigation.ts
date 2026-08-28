export const WORKSPACE_VIEWS = ['source', 'report', 'related', 'summary', 'chat'] as const

export type WorkspaceView = typeof WORKSPACE_VIEWS[number]

export interface WorkspaceLocation {
  taskId?: string
  view: WorkspaceView
  page?: number
  quote?: string
}

export interface WorkspaceResumeState {
  lastOpenedAt: string
  view: WorkspaceView
  page?: number
}

interface ReadingRecencyItem {
  createdAt?: string
  readingProgress?: WorkspaceResumeState
}

export function isWorkspaceView(value: string | null | undefined): value is WorkspaceView {
  return WORKSPACE_VIEWS.includes(value as WorkspaceView)
}

export function parseWorkspaceLocation(search: string | URLSearchParams): WorkspaceLocation {
  const params = typeof search === 'string'
    ? new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
    : search
  const rawPage = Number.parseInt(params.get('page') || '', 10)
  const rawView = params.get('view')

  return {
    taskId: params.get('task_id') || undefined,
    view: isWorkspaceView(rawView) ? rawView : 'source',
    page: Number.isInteger(rawPage) && rawPage > 0 ? rawPage : undefined,
    quote: params.get('quote')?.trim() || undefined,
  }
}

export function buildWorkspaceSearch(location: WorkspaceLocation): string {
  const params = new URLSearchParams()
  if (location.taskId) params.set('task_id', location.taskId)
  params.set('view', location.view)
  if (location.view === 'source' && location.page) params.set('page', String(location.page))
  if (location.view === 'source' && location.quote?.trim()) params.set('quote', location.quote.trim())
  return params.toString()
}

export function updateWorkspaceResumeState(
  current: WorkspaceResumeState | undefined,
  location: Pick<WorkspaceLocation, 'view' | 'page'>,
  lastOpenedAt = new Date().toISOString(),
): WorkspaceResumeState {
  return {
    lastOpenedAt,
    view: location.view,
    page: location.view === 'source' && location.page ? location.page : current?.page,
  }
}

export function workspaceLocationFromResume(
  taskId: string,
  resume: WorkspaceResumeState | undefined,
  fallbackView: WorkspaceView = 'source',
): WorkspaceLocation {
  const view = resume?.view || fallbackView
  return {
    taskId,
    view,
    page: view === 'source' ? resume?.page : undefined,
  }
}

function timestamp(value?: string): number {
  if (!value) return 0
  const parsed = new Date(value).getTime()
  return Number.isFinite(parsed) ? parsed : 0
}

export function compareReadingRecency(a: ReadingRecencyItem, b: ReadingRecencyItem): number {
  const aTime = timestamp(a.readingProgress?.lastOpenedAt) || timestamp(a.createdAt)
  const bTime = timestamp(b.readingProgress?.lastOpenedAt) || timestamp(b.createdAt)
  return bTime - aTime
}

export function findQuoteRange(text: string, quote: string): { start: number; end: number } | null {
  const needle = quote.trim()
  if (!text || !needle) return null

  const direct = text.toLocaleLowerCase().indexOf(needle.toLocaleLowerCase())
  if (direct >= 0) return { start: direct, end: direct + needle.length }

  const normalizedText: string[] = []
  const sourceIndexes: number[] = []
  let previousWasSpace = false

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    const isSpace = /\s/.test(char)
    if (isSpace) {
      if (previousWasSpace) continue
      normalizedText.push(' ')
      sourceIndexes.push(index)
      previousWasSpace = true
      continue
    }
    normalizedText.push(char.toLocaleLowerCase())
    sourceIndexes.push(index)
    previousWasSpace = false
  }

  const normalizedNeedle = needle.replace(/\s+/g, ' ').toLocaleLowerCase()
  const normalizedStart = normalizedText.join('').indexOf(normalizedNeedle)
  if (normalizedStart < 0) return null
  const normalizedEnd = normalizedStart + normalizedNeedle.length - 1
  return {
    start: sourceIndexes[normalizedStart],
    end: sourceIndexes[normalizedEnd] + 1,
  }
}

export interface WorkspaceCommandDetail {
  taskId?: string
  viewMode?: WorkspaceView
  page?: number
  quote?: string
  chat?: false | 'half' | 'full'
}

export function emitWorkspaceCommand(detail: WorkspaceCommandDetail) {
  window.dispatchEvent(new CustomEvent('fastread:workspace-command', { detail }))
}
