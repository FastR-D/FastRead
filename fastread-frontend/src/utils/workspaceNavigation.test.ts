import { describe, expect, it } from 'vitest'
import {
  buildWorkspaceSearch,
  compareReadingRecency,
  findQuoteRange,
  parseWorkspaceLocation,
  updateWorkspaceResumeState,
  workspaceLocationFromResume,
} from './workspaceNavigation'

describe('workspace navigation', () => {
  it('round-trips a page citation without losing unicode quotes', () => {
    const search = buildWorkspaceSearch({
      taskId: 'paper-1',
      view: 'source',
      page: 12,
      quote: '这是 exact quote。',
    })

    expect(parseWorkspaceLocation(search)).toEqual({
      taskId: 'paper-1',
      view: 'source',
      page: 12,
      quote: '这是 exact quote。',
    })
  })

  it('drops page and quote outside the source view', () => {
    const search = buildWorkspaceSearch({ taskId: 'paper-1', view: 'report', page: 3, quote: 'ignored' })
    expect(search).toBe('task_id=paper-1&view=report')
  })

  it('finds a quote even when PDF extraction changes whitespace', () => {
    const text = 'The method\n\nuses   two stages for retrieval.'
    expect(findQuoteRange(text, 'method uses two stages')).toEqual({ start: 4, end: 29 })
  })

  it('keeps the last source page while the reader moves through other workspace views', () => {
    const sourceState = updateWorkspaceResumeState(
      undefined,
      { view: 'source', page: 8 },
      '2026-08-09T08:00:00.000Z',
    )
    const reportState = updateWorkspaceResumeState(
      sourceState,
      { view: 'report' },
      '2026-08-09T09:00:00.000Z',
    )

    expect(reportState).toEqual({
      lastOpenedAt: '2026-08-09T09:00:00.000Z',
      view: 'report',
      page: 8,
    })
    expect(buildWorkspaceSearch(workspaceLocationFromResume('paper-1', reportState))).toBe(
      'task_id=paper-1&view=report',
    )
    expect(buildWorkspaceSearch(workspaceLocationFromResume('paper-1', sourceState))).toBe(
      'task_id=paper-1&view=source&page=8',
    )
  })

  it('sorts recent reading by last opened time before falling back to creation time', () => {
    const tasks = [
      { id: 'new-but-unopened', createdAt: '2026-08-09T10:00:00.000Z' },
      {
        id: 'continued',
        createdAt: '2026-08-01T10:00:00.000Z',
        readingProgress: {
          lastOpenedAt: '2026-08-09T11:00:00.000Z',
          view: 'source' as const,
          page: 12,
        },
      },
    ]

    expect(tasks.sort(compareReadingRecency).map(task => task.id)).toEqual([
      'continued',
      'new-but-unopened',
    ])
  })
})
