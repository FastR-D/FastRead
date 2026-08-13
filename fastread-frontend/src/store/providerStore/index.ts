import { create } from 'zustand'
import { IProvider } from '@/types'
import {
  addProvider,
  getProviderById,
  getProviderList,
  updateProviderById,
} from '@/services/model.ts'

interface ProviderStore {
  provider: IProvider[]
  setProvider: (provider: IProvider) => void
  setAllProviders: (providers: IProvider[]) => void
  getProviderById: (id: string) => IProvider | undefined
  getProviderList: () => IProvider[]
  fetchProviderList: () => Promise<void>
  loadProviderById: (id: string) => Promise<IProvider | undefined>
  addNewProvider: (provider: Partial<IProvider>) => Promise<string>
  updateProvider: (provider: Partial<IProvider> & { id: string }) => Promise<void>
}

type ApiProvider = {
  id: string
  name: string
  logo?: string
  api_key?: string
  base_url?: string
  type: string
  enabled: number
}

function fromApiProvider(item: ApiProvider): IProvider {
  return {
    id: item.id,
    name: item.name,
    logo: item.logo || 'custom',
    apiKey: item.api_key || '',
    baseUrl: item.base_url || '',
    type: item.type,
    enabled: item.enabled,
  }
}

function isMaskedApiKey(value?: string): boolean {
  return Boolean(value && (/^\*+$/.test(value) || /^.{4}\*+.{4}$/.test(value)))
}

export const useProviderStore = create<ProviderStore>((set, get) => ({
  provider: [],

  // 添加或更新一个 provider
  setProvider: newProvider =>
    set(state => {
      const exists = state.provider.find(p => p.id === newProvider.id)
      if (exists) {
        return {
          provider: state.provider.map(p => (p.id === newProvider.id ? newProvider : p)),
        }
      } else {
        return { provider: [...state.provider, newProvider] }
      }
    }),

  // 设置整个 provider 列表
  setAllProviders: providers => set({ provider: providers }),
  loadProviderById: async (id: string) => {
    const item = await getProviderById(id) as unknown as ApiProvider | null
    return item ? fromApiProvider(item) : undefined

  },
  addNewProvider: async (provider: Partial<IProvider>) => {
    const payload = {
      ...provider,
      api_key: provider.apiKey,
      base_url: provider.baseUrl,
    }
    try {
      const id = await addProvider(payload) as unknown as string
      await get().fetchProviderList()
      return id
    } catch (error) {
      console.error('Error fetching provider:', error)
      throw error
    }
  },
  // 按 id 获取单个 provider
  getProviderById: id => get().provider.find(p => p.id === id),
  updateProvider: async (provider: Partial<IProvider> & { id: string }) => {
    try {
      const existing = get().provider.find(p => p.id === provider.id)
      const merged = { ...existing, ...provider }

      const data: Record<string, unknown> = {
        ...merged,
        base_url: merged.baseUrl,
      }
      if (merged.apiKey && !isMaskedApiKey(merged.apiKey))
        data.api_key = merged.apiKey
      // 拦截器已解包：成功时直接返回 data 部分
      await updateProviderById(data)
      await get().fetchProviderList()
    } catch (error) {
      console.error('Error updating provider:', error)
      throw error
    }
  },
  getProviderList: () => get().provider,
  fetchProviderList: async () => {
    try {
      const res = await getProviderList() as unknown as ApiProvider[]

        set({
          provider: Array.isArray(res) ? res.map(fromApiProvider) : [],
        })
    } catch (error) {
      console.error('Error fetching provider list:', error)
    }
  },
}))
