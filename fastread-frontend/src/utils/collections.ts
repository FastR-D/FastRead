export const DEFAULT_COLLECTION_FOLDER = '默认收藏夹'
export const COLLECTION_FOLDER_MAX_CHARS = 80

export const normalizeCollectionFolder = (value: string): string =>
  String(value || '').normalize('NFC').trim().replace(/\s+/gu, ' ')

export const validateCollectionFolder = (value: string): string | null => {
  const normalized = normalizeCollectionFolder(value)
  if (!normalized) return '收藏夹名称不能为空'
  if (Array.from(normalized).length > COLLECTION_FOLDER_MAX_CHARS) {
    return `收藏夹名称不能超过 ${COLLECTION_FOLDER_MAX_CHARS} 个字符`
  }
  return null
}

export const collectionFolderKey = (value: string): string =>
  normalizeCollectionFolder(value).toLocaleLowerCase()

export const mergeCollectionFolders = (
  registeredFolders: readonly string[],
  taskFolders: readonly string[] = [],
): string[] => {
  const folders = new Map<string, string>()
  const append = (value: string) => {
    const normalized = normalizeCollectionFolder(value)
    if (!normalized || validateCollectionFolder(normalized)) return
    const key = collectionFolderKey(normalized)
    if (!folders.has(key)) folders.set(key, normalized)
  }

  append(DEFAULT_COLLECTION_FOLDER)
  registeredFolders.forEach(append)
  taskFolders.forEach(append)

  return Array.from(folders.values()).sort((left, right) => {
    if (left === DEFAULT_COLLECTION_FOLDER) return -1
    if (right === DEFAULT_COLLECTION_FOLDER) return 1
    return left.localeCompare(right, 'zh-CN')
  })
}
