import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  deleteCollection: vi.fn(),
  updateCollection: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('@/services/note.ts', () => ({
  delete_collection_folder: mocks.deleteCollection,
  delete_paper: vi.fn(),
  list_generated_tasks: vi.fn().mockResolvedValue([]),
  update_task_collection: mocks.updateCollection,
}))

vi.mock('idb-keyval', () => ({
  get: vi.fn().mockResolvedValue(null),
  set: vi.fn().mockResolvedValue(undefined),
  del: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('react-hot-toast', () => ({
  default: {
    success: mocks.toastSuccess,
    error: mocks.toastError,
  },
}))

import { useTaskStore } from './index'

const addPaper = () => {
  useTaskStore.getState().addPendingTask('paper-1', {
    source_url: 'https://arxiv.org/pdf/2601.00001.pdf',
    model_name: 'model',
    provider_id: 'provider',
  })
}

describe('collection persistence feedback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.updateCollection.mockResolvedValue({})
    mocks.deleteCollection.mockResolvedValue({ updated_task_ids: [], updated_count: 0 })
    useTaskStore.setState({
      tasks: [],
      currentTaskId: null,
      collectionFolders: ['默认收藏夹'],
      collectionSync: {},
    })
    addPaper()
  })

  it('records successful folder and tag saves', async () => {
    mocks.updateCollection.mockResolvedValue({})
    useTaskStore.getState().updateTaskCollection('paper-1', {
      folder: '大模型安全',
      tags: ['prompt-injection', 'survey'],
      note: '组会阅读',
    })

    expect(useTaskStore.getState().collectionSync['paper-1'].status).toBe('dirty')
    await useTaskStore.getState().saveTaskCollection('paper-1')

    expect(mocks.updateCollection).toHaveBeenCalledWith({
      task_id: 'paper-1',
      collection_folder: '大模型安全',
      collection_tags: ['prompt-injection', 'survey'],
      collection_note: '组会阅读',
    })
    expect(useTaskStore.getState().collectionSync['paper-1'].status).toBe('saved')
    expect(mocks.toastSuccess).toHaveBeenCalledWith('收藏夹和标签已保存')
  })

  it('keeps the optimistic edit and exposes a retryable error', async () => {
    mocks.updateCollection.mockRejectedValueOnce(new Error('backend unavailable'))
    useTaskStore.getState().updateTaskCollection('paper-1', {
      folder: '待读',
      tags: ['acl'],
    })

    await expect(useTaskStore.getState().saveTaskCollection('paper-1')).rejects.toThrow('backend unavailable')

    const state = useTaskStore.getState()
    expect(state.tasks[0].collection.folder).toBe('待读')
    expect(state.tasks[0].collection.tags).toEqual(['acl'])
    expect(state.collectionSync['paper-1']).toMatchObject({ status: 'error', message: 'backend unavailable' })
    expect(mocks.toastError).toHaveBeenCalledWith('收藏信息保存失败，可在资料库重试')
  })

  it('keeps an explicit editor draft out of task state until the API save succeeds', async () => {
    let finishSave: (() => void) | undefined
    mocks.updateCollection.mockReturnValueOnce(new Promise<void>(resolve => { finishSave = resolve }))

    const saving = useTaskStore.getState().saveTaskCollection('paper-1', {
      folder: '  本周   必读  ',
      tags: [' survey ', 'survey', ''],
      note: '组会',
    })

    expect(useTaskStore.getState().tasks[0].collection.folder).toBe('默认收藏夹')
    finishSave?.()
    await saving

    expect(mocks.updateCollection).toHaveBeenCalledWith({
      task_id: 'paper-1',
      collection_folder: '本周 必读',
      collection_tags: ['survey'],
      collection_note: '组会',
    })
    expect(useTaskStore.getState().tasks[0].collection.folder).toBe('本周 必读')
    expect(useTaskStore.getState().collectionFolders).toContain('本周 必读')
  })

  it('rejects an empty folder without mutating or calling the API', async () => {
    await expect(useTaskStore.getState().saveTaskCollection('paper-1', {
      folder: '   ',
      tags: [],
      note: '',
    })).rejects.toThrow('收藏夹名称不能为空')

    expect(mocks.updateCollection).not.toHaveBeenCalled()
    expect(useTaskStore.getState().tasks[0].collection.folder).toBe('默认收藏夹')
  })

  it('does not apply an explicit editor draft when its save fails', async () => {
    mocks.updateCollection.mockRejectedValueOnce(new Error('backend unavailable'))

    await expect(useTaskStore.getState().saveTaskCollection('paper-1', {
      folder: '组会必读',
      tags: ['acl'],
      note: '',
    })).rejects.toThrow('backend unavailable')

    expect(useTaskStore.getState().tasks[0].collection.folder).toBe('默认收藏夹')
    expect(useTaskStore.getState().collectionFolders).not.toContain('组会必读')
  })

  it('persists empty folders locally and rejects normalized duplicate names', () => {
    expect(useTaskStore.getState().createCollectionFolder('  AI   Safety  ')).toBe('AI Safety')
    expect(useTaskStore.getState().collectionFolders).toContain('AI Safety')

    expect(() => useTaskStore.getState().createCollectionFolder('ai safety')).toThrow('收藏夹名称已存在')
    expect(() => useTaskStore.getState().createCollectionFolder('  ')).toThrow('收藏夹名称不能为空')
  })

  it('atomically deletes a folder and moves its papers back to the default folder', async () => {
    useTaskStore.setState(state => ({
      tasks: state.tasks.map(task => ({
        ...task,
        collection: { ...task.collection, folder: '本周必读' },
      })),
      collectionFolders: ['默认收藏夹', '本周必读'],
    }))

    await useTaskStore.getState().deleteCollectionFolder('本周必读')

    expect(mocks.deleteCollection).toHaveBeenCalledWith('本周必读')
    expect(useTaskStore.getState().tasks[0].collection.folder).toBe('默认收藏夹')
    expect(useTaskStore.getState().collectionFolders).toEqual(['默认收藏夹'])
    expect(mocks.toastSuccess).toHaveBeenCalledWith('收藏夹已删除，1 篇论文已移回默认收藏夹')
  })

  it('keeps local assignments unchanged when folder deletion fails', async () => {
    mocks.deleteCollection.mockRejectedValueOnce(new Error('backend unavailable'))
    useTaskStore.setState(state => ({
      tasks: state.tasks.map(task => ({
        ...task,
        collection: { ...task.collection, folder: '稍后阅读' },
      })),
      collectionFolders: ['默认收藏夹', '稍后阅读'],
    }))

    await expect(useTaskStore.getState().deleteCollectionFolder('稍后阅读')).rejects.toThrow('backend unavailable')

    expect(useTaskStore.getState().tasks[0].collection.folder).toBe('稍后阅读')
    expect(useTaskStore.getState().collectionFolders).toContain('稍后阅读')
    expect(mocks.toastError).toHaveBeenCalledWith('收藏夹删除失败，未更改本地分类')
  })

  it('protects the default folder from deletion', async () => {
    await expect(useTaskStore.getState().deleteCollectionFolder('默认收藏夹')).rejects.toThrow('默认收藏夹不能删除')
    expect(mocks.deleteCollection).not.toHaveBeenCalled()
  })
})
