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
  abstract?: string
  keywords?: string[]
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
  cited_by?: number | null
  full_text_verified?: boolean
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

export type SmartNeighborRole =
  | 'direct_competitor'
  | 'same_problem_different_method'
  | 'same_method_different_problem'
  | 'evaluation_or_control_neighbor'
  | 'background'

export type SmartNeighborSelectionItem = {
  candidate_id: string
  role: SmartNeighborRole
  reason: string
  contrast: string
  scores: {
    research_problem: number
    method: number
    evidence: number
    novelty_threat: number
  }
  semantic_score: number
  combined_score: number
}

export type SmartNeighborSelection = {
  id: string
  task_id: string
  snapshot_id: string
  cache_key: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  provider_id: string
  model_name: string
  prompt_version: string
  strategy_version: string
  candidate_count: number
  selected_count: number
  metadata: {
    candidate_hash?: string
    selection_limit?: number
    evidence_boundary?: string
    validation?: string
    code_filter?: {
      minimum_combined_score: number
      maximum_background_items: number
    }
    context_policy?: {
      policy_version: string
      source_page_count: number
      included_page_count: number
      context_characters: number
    }
  }
  selections: SmartNeighborSelectionItem[]
  failure_reason: string
  error: string
  created_at: string
  started_at: string
  completed_at: string
  scheduled?: boolean
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

export const getSmartNeighborSelection = (taskId: string): Promise<SmartNeighborSelection | null> =>
  request.get(`/papers/${encodeURIComponent(taskId)}/related-work/smart-selection`) as any

export const startSmartNeighborSelection = (
  taskId: string,
  options: { provider_id: string; model_name: string; force?: boolean; selection_limit?: number },
): Promise<SmartNeighborSelection> =>
  request.post(`/papers/${encodeURIComponent(taskId)}/related-work/smart-selection`, options, { timeout: 12000 }) as any
