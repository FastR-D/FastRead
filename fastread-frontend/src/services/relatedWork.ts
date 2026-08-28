import request from '@/utils/request'

export type RelatedWorkAnchor = {
  anchor_id: string
  kind: 'research_question' | 'method' | 'contribution' | 'fallback'
  text: string
  report_version: string
  pages: number[]
}

export type RelatedWorkNeighbor = {
  canonical_paper_id: string
  title: string
  authors: string[]
  year?: number | null
  venue: string
  doi: string
  official_url: string
  arxiv_url: string
  pdf_url: string
  matched_anchor_ids: string[]
  overlapping_terms: string[]
  relevance_score: number
  source_role?: 'primary' | 'supplemental'
  discovery_channel?: 'arxiv' | 'elasticsearch' | 'supplemental'
  provenance: {
    provider: string
    retrieved_at: string
    metadata_only: boolean
    note?: string
    source_page?: number
    exact_quote?: string
  }
}

export type RelatedWorkProviderStatus = {
	configured?: boolean
	available?: boolean
	status?: string
	reason?: string
	error?: string
	result_count?: number
	manual_search_url?: string
	provider?: string
	http_status?: number
	query_count?: number
	via_proxy?: boolean
}

export type RelatedWorkSnapshot = {
  id: string
  paper_id: string
  paper_content_hash: string
  report_version: string
  anchors: RelatedWorkAnchor[]
  queries?: string[]
  neighbors: RelatedWorkNeighbor[]
	provider_status: Record<string, RelatedWorkProviderStatus>
  search_backend: string
  search_keywords?: string[]
  result_limit?: number
  source_counts?: Record<'arxiv' | 'elasticsearch' | 'supplemental', number>
  search_policy?: {
    mode: 'keyword_first'
    primary_channels: string[]
    supplemental_channels: string[]
  }
  generated_at: string
  cache_hit?: boolean
}

export const getRelatedWork = (taskId: string): Promise<RelatedWorkSnapshot | null> =>
  request.get(`/papers/${encodeURIComponent(taskId)}/related-work`) as any

export const generateRelatedWork = (
  taskId: string,
  options: { force?: boolean; limit?: number } = {},
): Promise<RelatedWorkSnapshot> =>
  request.post(`/papers/${encodeURIComponent(taskId)}/related-work`, options, { timeout: 12000 }) as any
