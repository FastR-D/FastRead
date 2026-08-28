export interface SummaryDraft {
  content: string
  updatedAt: string
}

export function summaryDraftKey(taskId: string) {
  return `fastread:personal-summary-draft:${taskId}`
}

export function loadSummaryDraft(taskId: string, storage: Pick<Storage, 'getItem'> = localStorage): SummaryDraft | null {
  try {
    const value = storage.getItem(summaryDraftKey(taskId))
    if (!value) return null
    const draft = JSON.parse(value) as Partial<SummaryDraft>
    if (typeof draft.content !== 'string' || typeof draft.updatedAt !== 'string') return null
    return { content: draft.content, updatedAt: draft.updatedAt }
  }
  catch {
    return null
  }
}

export function saveSummaryDraft(
  taskId: string,
  content: string,
  storage: Pick<Storage, 'setItem'> = localStorage,
): SummaryDraft {
  const draft = { content, updatedAt: new Date().toISOString() }
  storage.setItem(summaryDraftKey(taskId), JSON.stringify(draft))
  return draft
}

export function removeSummaryDraft(taskId: string, storage: Pick<Storage, 'removeItem'> = localStorage) {
  storage.removeItem(summaryDraftKey(taskId))
}
