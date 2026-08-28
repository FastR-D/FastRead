import { describe, expect, it } from 'vitest'
import { migratePaperTaskState } from './index'


describe('paper-only persisted task migration', () => {
  it('keeps only explicit paper tasks and their reading position', () => {
    const migrated = migratePaperTaskState({
      tasks: [
        {
          id: 'paper-1',
          kind: 'paper',
          readingProgress: { view: 'related', page: 7, lastOpenedAt: '2026-08-28T00:00:00Z' },
        },
        { id: 'retired-media', kind: 'retired-media' },
        { id: 'retired-check', kind: 'retired-check' },
        { id: 'missing-kind' },
      ],
      currentTaskId: 'paper-1',
      collectionSync: { 'paper-1': { status: 'dirty' } },
    })

    expect(migrated.tasks.map(task => task.id)).toEqual(['paper-1'])
    expect(migrated.tasks[0].readingProgress).toMatchObject({ view: 'related', page: 7 })
    expect(migrated.currentTaskId).toBe('paper-1')
    expect(migrated.collectionSync).toEqual({})
  })

  it('clears a selected task when that task was retired', () => {
    const migrated = migratePaperTaskState({
      tasks: [{ id: 'legacy', kind: 'retired-check' }],
      currentTaskId: 'legacy',
    })

    expect(migrated.tasks).toEqual([])
    expect(migrated.currentTaskId).toBeNull()
  })

  it('keeps registered empty folders and discovers folders from migrated papers', () => {
    const migrated = migratePaperTaskState({
      tasks: [
        {
          id: 'paper-1',
          kind: 'paper',
          collection: { folder: '组会必读', tags: [], note: '' },
        },
      ],
      collectionFolders: ['空收藏夹'],
    })

    expect(migrated.collectionFolders).toEqual(['默认收藏夹', '空收藏夹', '组会必读'])
  })
})
