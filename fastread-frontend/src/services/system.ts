import request from '@/utils/request'

export const systemCheck = async () => {
  return await request.get('/sys_health')
}

export interface DeployStatus {
  backend: {
    status: string
    port: number
  }
  database: {
    available: boolean
    path: string
  }
  storage: {
    paper_results: boolean
    uploads: boolean
  }
  runtime: {
    python: string
    platform: string
  }
  errors: string[]
}

export const getDeployStatus = async (): Promise<DeployStatus> => {
  return await request.get('/deploy_status')
}

export interface PaperSearchConfig {
  paper_search_proxy_url: string
  google_scholar_api_url: string
  serpapi_api_key_configured: boolean
  elasticsearch_url: string
}

export interface PaperSearchConfigUpdate {
  paper_search_proxy_url: string
  google_scholar_api_url: string
  serpapi_api_key?: string
  clear_serpapi_api_key?: boolean
  elasticsearch_url: string
}

export const getPaperSearchConfig = async (): Promise<PaperSearchConfig> => {
  return await request.get('/paper_search_config') as unknown as PaperSearchConfig
}

export const updatePaperSearchConfig = async (data: PaperSearchConfigUpdate): Promise<PaperSearchConfig> => {
  return await request.put('/paper_search_config', data) as unknown as PaperSearchConfig
}
