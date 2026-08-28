import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  updateCollection: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('@/services/note.ts', () => ({
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
    useTaskStore.setState({ tasks: [], currentTaskId: null, collectionSync: {} })
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
})
