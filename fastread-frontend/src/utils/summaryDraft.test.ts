import { describe, expect, it } from 'vitest'
import { loadSummaryDraft, removeSummaryDraft, saveSummaryDraft, summaryDraftKey } from './summaryDraft'

function memoryStorage() {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  }
}

describe('personal summary drafts', () => {
  it('keeps independent drafts for each paper', () => {
    const storage = memoryStorage()
    saveSummaryDraft('a', 'paper A', storage)
    saveSummaryDraft('b', 'paper B', storage)

    expect(loadSummaryDraft('a', storage)?.content).toBe('paper A')
    expect(loadSummaryDraft('b', storage)?.content).toBe('paper B')
  })

  it('removes a draft after the server save succeeds', () => {
    const storage = memoryStorage()
    saveSummaryDraft('a', 'saved', storage)
    removeSummaryDraft('a', storage)
    expect(storage.getItem(summaryDraftKey('a'))).toBeNull()
  })
})
