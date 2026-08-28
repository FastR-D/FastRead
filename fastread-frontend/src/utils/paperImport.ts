export interface PaperImportModelLike {
  provider_id?: string | null
  model_name?: string | null
}

export interface PaperImportModelFields {
  provider_id: string
  model_name: string
}

export function paperImportModelFields(model?: PaperImportModelLike | null): PaperImportModelFields {
  const providerId = String(model?.provider_id || '').trim()
  const modelName = String(model?.model_name || '').trim()

  if (!providerId || !modelName) {
    return { provider_id: '', model_name: '' }
  }

  return { provider_id: providerId, model_name: modelName }
}
