import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(new URL('./index.tsx', import.meta.url), 'utf8')

describe('library collection navigation', () => {
  it('keeps folder and tag filters visible in the primary library', () => {
    for (const copy of ['收藏目录', '全部收藏夹', '全部标签', '收藏夹与标签']) {
      expect(source).toContain(copy)
    }
  })

  it('shows save, error, and retry states instead of console-only failure', () => {
    for (const copy of ['保存', "collectionState?.status === 'error'", '取消']) {
      expect(source).toContain(copy)
    }
  })

  it('uses an editable draft so clearing a name is not replaced by the default folder', () => {
    expect(source).toContain('value={collectionDraft.folder}')
    expect(source).toContain('saveTaskCollection(collectionTask.id, nextCollection)')
    expect(source).not.toContain("value={collectionTask.collection?.folder || '默认收藏夹'}")
  })

  it('lists every existing folder before offering a custom folder name', () => {
    expect(source).toContain('aria-label="选择已有收藏夹"')
    expect(source).toContain('{folders.map(folder => <option key={folder} value={folder}>{folder}</option>)}')
    expect(source).toContain('＋ 输入新收藏夹名称…')
    expect(source).toContain('aria-label="新收藏夹名称"')
    expect(source).not.toContain('<datalist')
  })

  it('exposes create, switch, move-out, and safe folder deletion actions', () => {
    for (const copy of ['新建收藏夹', '移出当前收藏夹', '删除当前收藏夹', '论文本身不会删除']) {
      expect(source).toContain(copy)
    }
    expect(source).toContain('setFolderFilter(ALL_COLLECTIONS)')
  })
})
