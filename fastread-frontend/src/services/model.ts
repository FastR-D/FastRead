import request from '@/utils/request.ts'

export interface ApiProvider {
  id: string
  name: string
  logo?: string
  api_key?: string
  base_url?: string
  type: string
  enabled: number
}

export interface EnabledModel {
  id: string
  provider_id: string
  model_name: string
  created_at?: string
}

export interface RemoteModel {
  id: string
  created: number
  object: string
  owned_by: string
  permission: string
  root: string
}

export interface RemoteModelList {
  models: RemoteModel[] | { data: RemoteModel[] }
}

export const getProviderList = async (): Promise<ApiProvider[]> => {
  return await request.get('/get_all_providers') as unknown as ApiProvider[]
}

export const getProviderById = async (id: string): Promise<ApiProvider | null> => {
  return await request.get(`/get_provider_by_id/${id}`) as unknown as ApiProvider | null
}

export const updateProviderById = async (data: Record<string, unknown>): Promise<void> => {
  await request.post('/update_provider', data)
}

export const addProvider = async (data: Record<string, unknown>): Promise<string> => {
  return await request.post('/add_provider', data) as unknown as string
}

export const testConnection = async (data: { id: string }): Promise<void> => {
  await request.post('/connect_test', data)
}

export const fetchModels = async (providerId: string): Promise<RemoteModelList> => {
  return await request.get('/model_list/' + providerId) as unknown as RemoteModelList
}

export const fetchEnableModelById = async (id: string): Promise<EnabledModel[]> => {
  return await request.get('/model_enable/' + id) as unknown as EnabledModel[]
}

export async function addModel(data: { provider_id: string; model_name: string }): Promise<Partial<EnabledModel>> {
  return await request.post('/models', data) as unknown as Partial<EnabledModel>
}

export const fetchEnableModels = async (): Promise<EnabledModel[]> => {
  return await request.get('/model_list') as unknown as EnabledModel[]
}

export const deleteModelById = async (modelId: string | number): Promise<unknown> => {
  return await request.get(`/models/delete/${modelId}`) as unknown
}
