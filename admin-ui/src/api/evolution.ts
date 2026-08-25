import { get } from './request'
import { post } from './request'

export interface EvolutionSummary {
  tasks_total: number
  decision_events: number
  experiences_total: number
  role_reflections_total?: number
  avg_evaluation_score: number | null
  success_rate: number | null
  override_hits?: number
  override_success_rate?: number | null
}

export interface EvolutionDecisionEvent {
  task_id: string
  tenant_id?: string
  task_type: string
  status: string
  created_at: string
  capability_id?: string
  strategy_id?: string
  strategy_score?: number | null
  strategy_reasons?: string[]
  strategy_runtime_adjustments?: {
    override_active?: boolean
    weight_delta?: number
    preferred?: boolean
    blocked?: boolean
    source?: string
    updated_at?: string
    expires_at?: string
    growth_memory_bias?: number
    platform_shared_bias?: number
    platform_shared_hits?: number
    platform_shared_titles?: string[]
  }
  evaluation_score?: number | null
  evaluation_verdict?: string
  evaluation_reasons?: string[]
  evaluation_metrics?: Record<string, number | string | boolean>
  history_size?: number
  summary?: string
  candidate_scores?: Array<{
    capability_id?: string
    score: number
    reasons: string[]
  }>
  error?: string | null
  issue_category?: string
  issue_hints?: string[]
  recommended_actions?: string[]
  replay_of?: string
}

export interface EvolutionExperience {
  id: string
  domain: string
  task_type: string
  quality_score: number
  created_at: string
  strategy_id?: string
  evaluation_verdict?: string
  evaluation_score?: number | null
  output_summary: string
  experience_kind?: 'execution' | 'role_reflection'
  member_id?: string
  member_name?: string
  primary_role?: string
  stage?: string
  status?: string
}

export interface RoleReflectionExperience {
  id: string
  created_at: string
  member_id?: string
  member_name?: string
  primary_role?: string
  domain: string
  quality_score: number
  summary: string
  stage?: string
  status?: string
  next_experiment?: string
}

export interface ReplayValidation {
  id: string
  created_at: string
  quality_score: number
  output_summary: string
  original_task_id?: string
  replay_task_id?: string
  score_delta?: number | null
  outcome?: string
  strategy_id?: string
}

export interface GrowthEvent {
  id: string
  created_at: string
  quality_score: number
  output_summary: string
  strategy_id?: string
  event_type?: string
  task_type?: string
  domain?: string
  member_id?: string
  member_name?: string
  primary_role?: string
  mission_run_id?: string
  mission_status?: string
  training_stage_from?: string
  training_stage_to?: string
  next_action?: string
}

export interface PositiveStrategy {
  strategy_id: string
  count: number
  total_gain: number
  avg_gain: number
}

export interface StrategyAlert {
  strategy_id: string
  count: number
  review_ratio: number
  avg_eval: number
  total_gain: number
  alert_reason: string
}

export interface StrategyReviewQueueItem {
  id: string
  strategy_id: string
  status: string
  created_at: string
  reason?: string
  alert_reason?: string
  count?: number
  review_ratio?: number
  avg_eval?: number
  total_gain?: number
  notes?: string
  draft_generated_at?: string
  draft?: {
    summary: string
    goals: string[]
    hypotheses: string[]
    proposed_changes: string[]
    validation_plan: string[]
  }
  experiment_generated_at?: string
  experiment_plan?: {
    title: string
    linked_draft_summary?: string
    sample_count: number
    steps: string[]
    acceptance_criteria: string[]
    next_action: string
  }
  last_run_at?: string
  experiment_runs?: Array<{
    created_at: string
    plan_title?: string
    sample_count_requested: number
    sample_count_actual: number
    source_task_ids: string[]
    task_ids: string[]
    summary?: {
      status: string
      completed: number
      pending: number
      success: number
      review: number
      failed: number
      avg_score?: number | null
      baseline_avg_score?: number | null
      score_delta?: number | null
      improved_count: number
      regressed_count: number
      unchanged_count: number
      recommended_action: string
    }
  }>
  upgrade_candidate?: {
    generated_at: string
    title: string
    summary: string
    rationale: string[]
    proposed_actions: string[]
    risk_checks: string[]
    decision: string
    decision_note?: string
    decided_at?: string | null
  }
  platform_promotion?: {
    status: string
    promoted_at?: string
    path?: string
  }
}

export interface PlatformSharedPromotionItem {
  id: string
  tenant_id?: string
  strategy_id?: string
  promoted_at?: string
  path?: string
  share_mode?: string
  decision?: string
  title?: string
  summary?: string
}

export interface KnowledgeLayerAdvice {
  headline: string
  overall_stage: 'private_growth' | 'project_review' | 'platform_shared'
  overall_status: string
  recommended_next_layer: 'private_growth' | 'project_review' | 'platform_shared'
  recommendation_reason: string
  share_mode: string
  allow_platform_promotion: boolean
  review_required: boolean
  counts: {
    private_experiences: number
    review_queue: number
    platform_shared: number
    review_cases: number
  }
  layers: Array<{
    key: 'private_growth' | 'project_review' | 'platform_shared'
    label: string
    count: number
    status: string
    reason: string
    next_action: string
  }>
  next_actions: string[]
  recent_candidate_ids: string[]
  recent_experience_ids: string[]
}

export interface RankedItem {
  id: string
  count: number
}

export interface EvolutionOverview {
  tenant_id: string
  summary: EvolutionSummary
  domains: string[]
  plugin_policy: {
    enabled: string[]
    disabled: string[]
    loaded: string[]
  }
  knowledge_policy?: {
    share_mode: 'private_only' | 'reviewed_share' | 'platform_share'
    allow_platform_promotion: boolean
    review_required: boolean
  }
  knowledge_layer_advice?: KnowledgeLayerAdvice
  platform_promotion_status?: {
    allowed: boolean
    share_mode: string
    allow_platform_promotion: boolean
    review_required: boolean
    reason: string
  }
  strategy_overrides: Record<string, {
    weight_delta?: number
    preferred?: boolean
    blocked?: boolean
    source?: string
    note?: string
    updated_at?: string
    expires_at?: string
    active?: boolean
  }>
  override_stats: Record<string, {
    hits: number
    success: number
    review: number
    failed: number
    avg_eval?: number | null
    last_hit_at?: string | null
    source?: string
    weight_delta?: number
    preferred?: boolean
    expires_at?: string
    review_ratio?: number
    status?: string
  }>
  auto_rollback_events: Array<{
    strategy_id: string
    reason: string
    hits: number
    review_ratio: number
    avg_eval?: number | null
    source?: string
    rolled_back_at: string
    action: string
  }>
  growth_timeline: Array<{
    timestamp: string
    strategy_id?: string
    event_type: string
    title: string
    detail?: string
  }>
  top_capabilities: RankedItem[]
  top_strategies: RankedItem[]
  evaluation_verdicts: Record<string, number>
  review_category_counts: Record<string, number>
  recent_decisions: EvolutionDecisionEvent[]
  recent_experiences: EvolutionExperience[]
  recent_role_reflections: RoleReflectionExperience[]
  review_cases: EvolutionDecisionEvent[]
  replay_validations: ReplayValidation[]
  growth_events: GrowthEvent[]
  positive_strategies: PositiveStrategy[]
  strategy_alerts: StrategyAlert[]
  strategy_review_queue: StrategyReviewQueueItem[]
  auto_review_entries?: StrategyReviewQueueItem[]
  platform_shared_promotions?: PlatformSharedPromotionItem[]
}

export function getEvolutionOverview(tenantId: string) {
  return get<EvolutionOverview>(`/api/evolution/overview?tenant_id=${encodeURIComponent(tenantId)}`)
}

export function addStrategyReviewQueue(
  tenantId: string,
  payload: Record<string, unknown>
) {
  return post<{ tenant_id: string; entry: StrategyReviewQueueItem }>(
    `/api/tenants/${encodeURIComponent(tenantId)}/strategy-review-queue`,
    payload
  )
}

export function generateStrategyReviewDraft(tenantId: string, reviewId: string) {
  return post<{ tenant_id: string; entry: StrategyReviewQueueItem }>(
    `/api/tenants/${encodeURIComponent(tenantId)}/strategy-review-queue/${encodeURIComponent(reviewId)}/draft`,
    {}
  )
}

export function generateStrategyReviewExperiment(tenantId: string, reviewId: string) {
  return post<{ tenant_id: string; entry: StrategyReviewQueueItem }>(
    `/api/tenants/${encodeURIComponent(tenantId)}/strategy-review-queue/${encodeURIComponent(reviewId)}/experiment`,
    {}
  )
}

export function runStrategyReviewExperiment(tenantId: string, reviewId: string) {
  return post<{ tenant_id: string; entry: StrategyReviewQueueItem }>(
    `/api/tenants/${encodeURIComponent(tenantId)}/strategy-review-queue/${encodeURIComponent(reviewId)}/run`,
    {}
  )
}

export function decideStrategyUpgradeCandidate(
  tenantId: string,
  reviewId: string,
  decision: 'accept' | 'observe' | 'reject'
) {
  return post<{ tenant_id: string; entry: StrategyReviewQueueItem }>(
    `/api/tenants/${encodeURIComponent(tenantId)}/strategy-review-queue/${encodeURIComponent(reviewId)}/upgrade/${encodeURIComponent(decision)}`,
    {}
  )
}

export function promoteStrategyReviewToPlatform(tenantId: string, reviewId: string) {
  return post<{ tenant_id: string; entry: StrategyReviewQueueItem }>(
    `/api/tenants/${encodeURIComponent(tenantId)}/strategy-review-queue/${encodeURIComponent(reviewId)}/promote`,
    {}
  )
}

export function rollbackStrategyOverride(tenantId: string, strategyId: string) {
  return post<{
    tenant_id: string
    strategy_id: string
    strategy_overrides: EvolutionOverview['strategy_overrides']
  }>(
    `/api/tenants/${encodeURIComponent(tenantId)}/strategy-overrides/${encodeURIComponent(strategyId)}/rollback`,
    {}
  )
}

export function getPlatformSharedStrategyPromotions(limit = 20) {
  return get<{ items: PlatformSharedPromotionItem[] }>(
    `/api/platform-shared/strategy-promotions?limit=${encodeURIComponent(String(limit))}`
  )
}
