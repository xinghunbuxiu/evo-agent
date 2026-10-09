import { get, post, put } from './request'

export interface PluginManifest {
  name?: string
  version?: string
  compatibility?: Record<string, string>
  description?: string
  capability_types?: string[]
}

export interface PluginItem {
  name: string
  version: string
  capability_types: string[]
  manifest: PluginManifest
  capabilities: string[]
  strategies: string[]
  evaluators: string[]
  module_path: string
}

export interface TenantPluginPolicy {
  enabled: string[]
  disabled: string[]
}

export interface TenantKnowledgePolicy {
  share_mode: 'private_only' | 'reviewed_share' | 'platform_share'
  allow_platform_promotion: boolean
  review_required: boolean
}

export interface TenantModelProvider {
  enabled?: boolean
  label?: string
  base_url?: string
  api_key?: string
  api_key_configured?: boolean
  model?: string
}

export interface TenantExternalLearningPolicy {
  allow_ai_assist: boolean
  allow_web_research: boolean
  allow_enterprise_sources: boolean
  source_priority: string[]
  validation_required: boolean
  model_provider?: TenantModelProvider
}

export interface LearningCandidate {
  source: string
  title: string
  summary: string
  confidence: number
  evidence: string[]
  next_steps: string[]
  metadata?: Record<string, unknown>
}

export interface LearningTask {
  task_id: string
  tenant_id: string
  member_id?: string
  title?: string
  goal?: string
  mission_kind?: string
  source?: string
  work_type_id?: string
  gap_type?: string
  source_dir?: string
  bundle_path?: string
  sample_signature?: string
  issue_category?: string
  queries?: string[]
  preferred_sources?: string[]
  validation_gate?: string
  status: string
  source_runs?: Array<{
    source: string
    status: string
    candidate_count: number
  }>
  candidate_approaches?: LearningCandidate[]
  next_validation_action?: string
  updated_at?: string
  created_at?: string
  resolved_at?: string
  archived?: boolean
  auto_validation?: {
    status?: string
    source?: string
    review_id?: string
    triggered_at?: string
    attempted_at?: string
    finalized_at?: string
    created_task_ids?: string[]
    finalized_task_ids?: string[]
    validation_ids?: string[]
    reason?: string
  }
  comparison_history?: Array<{
    at?: string
    result?: string
    validation_ids?: string[]
  }>
  stable_cycle_count?: number
  stable_promoted_at?: string
  last_comparison?: {
    result?: string
    score_delta?: number | null
    outcome?: string
    replay_task_id?: string
    original_task_id?: string
  }
}

export interface EvolutionOverview {
  tenant_id?: string
  summary?: {
    total_tasks?: number
    avg_score?: number
    review_count?: number
    failed_count?: number
    promoted_count?: number
  }
  growth_timeline?: Array<{
    timestamp?: string
    strategy_id?: string
    event_type?: string
    title?: string
    detail?: string
  }>
  strategy_review_queue?: Array<{
    id: string
    strategy_id?: string
    status?: string
    alert_reason?: string
    notes?: string
    avg_eval?: number
    created_at?: string
    last_run_at?: string
    draft?: {
      summary?: string
      goals?: string[]
      proposed_changes?: string[]
      validation_plan?: string[]
    }
    experiment_plan?: {
      title?: string
      next_action?: string
      acceptance_criteria?: string[]
    }
    experiment_runs?: Array<{
      created_at?: string
      source_task_ids?: string[]
      task_ids?: string[]
      summary?: {
        status?: string
        avg_score?: number
        baseline_avg_score?: number
        score_delta?: number
        improved_count?: number
        regressed_count?: number
        unchanged_count?: number
        recommended_action?: string
      }
    }>
    upgrade_candidate?: {
      title?: string
      summary?: string
      decision?: string
      decision_note?: string
      decided_at?: string
      rationale?: string[]
    }
    platform_promotion?: {
      status?: string
      promoted_at?: string
      path?: string
    }
  }>
}

export interface PlatformSharedSeedItem {
  strategy_id: string
  title: string
  summary: string
  promoted_at?: string
  source_tenant_id?: string
  source_path?: string
  decision?: string
  share_mode?: string
  score: number
  reasons: string[]
  recommended_override: {
    weight_delta: number
    preferred: boolean
    blocked: boolean
    source: string
    note: string
  }
}

export interface SelfMediaGitExportRuntime {
  status?: string
  reason?: string
  token_available?: boolean
  repo_key?: string
  target_repo?: string
  target_url?: string
  branch?: string
  next_action?: string
  last_export?: {
    task_id?: string
    task_type?: string
    completed_at?: string
    status?: string
    reason?: string
    repo_key?: string
    repo_full_name?: string
    repo_url?: string
    branch?: string
    files?: string[]
  }
}

export interface SelfMediaTenantRuntimeState {
  account_id?: string
  topic?: string
  target_outcome?: string
  stage?: string
  blocked_reason?: string | null
  next_action?: string | null
  login_status?: string
  last_article_title?: string
  last_article_path?: string
  last_draft_task_id?: string
  last_draft_summary?: string
  last_task_id?: string
  last_task_status?: string
  last_checked_at?: string
  last_submitted_at?: string
  last_decision_at?: string
  analytics_completed_types?: string[]
  git_export?: SelfMediaGitExportRuntime
  account_snapshot?: Record<string, unknown>
  executor_snapshot?: Record<string, unknown>
  last_feedback_summary?: Record<string, unknown>
}

export interface ChildJobRuntimeState {
  job_id?: string
  account_id?: string
  status?: string
  blocked_reason?: string | null
  next_action?: string | null
  signals?: string[]
  account?: Record<string, unknown>
  tenant_state?: SelfMediaTenantRuntimeState
}

export interface ChildMemberRuntimeJob {
  job_id?: string
  title?: string
  status?: string
  priority?: string
  target_outcome?: string | null
  account_id?: string
  notes?: string | null
  runtime_state?: ChildJobRuntimeState
}

export interface MemberMemoryHubRetrievalPlanEntry {
  source?: string | null
  status?: string | null
  query?: string | null
  confidence?: number
  reason?: string | null
}

export interface MemberMemoryHubRetrievalHit {
  source?: string | null
  status?: string | null
  query?: string | null
  hits?: number
  best_match_summary?: string | null
  confidence?: number
  evidence?: string[]
  recommended_action?: string | null
}

export interface MemberMemoryHubDecisionSummary {
  summary?: string | null
  used_sources?: string[]
  primary_plan?: string | null
  fallback_plan?: string | null
  stop_reason?: string | null
  escalation_reason?: string | null
  verification_goal?: string | null
  expected_output?: string | null
  external_learning_required?: boolean
}

export interface MemberMemoryHubDecisionState {
  status?: string | null
  primary_plan?: string | null
  fallback_plan?: string | null
  stop_reason?: string | null
  escalation_reason?: string | null
  verification_goal?: string | null
  expected_output?: string | null
}

export interface MemberMemoryHubRetrievalState {
  preferred_sources?: string[]
  local_strength?: number
  needs_external_learning?: boolean
}

export interface MemberMemoryHubSnapshot {
  case_id?: string | null
  member_id?: string | null
  trigger?: string | null
  decision_intent?: string | null
  decision_confidence?: number
  created_at?: string | null
  decision_summary?: MemberMemoryHubDecisionSummary
  decision_state?: MemberMemoryHubDecisionState
  retrieval_state?: MemberMemoryHubRetrievalState & {
    retrieval_plan?: MemberMemoryHubRetrievalPlanEntry[]
    retrieval_hits?: MemberMemoryHubRetrievalHit[]
  }
}

export interface MemberMemoryHubRuntime {
  active_case_id?: string | null
  decision_intent?: string | null
  task_context?: Record<string, unknown>
  retrieval_plan?: MemberMemoryHubRetrievalPlanEntry[]
  retrieval_hits?: MemberMemoryHubRetrievalHit[]
  decision_summary?: MemberMemoryHubDecisionSummary
  decision_confidence?: number
  fallback_strategy?: string | null
  next_action?: string | null
  writeback_targets?: string[]
  last_run_at?: string | null
  last_trigger?: string | null
  preferred_sources?: string[]
  decision_state?: MemberMemoryHubDecisionState
  retrieval_state?: MemberMemoryHubRetrievalState
  last_decision_snapshot?: MemberMemoryHubSnapshot
  decision_history?: MemberMemoryHubSnapshot[]
}

export interface ChildMemberRuntimeProfile {
  member_id?: string
  name?: string
  status?: string
  archived_at?: string | null
  system_managed?: boolean
  identity_type?: string
  primary_role?: string
  persona?: {
    role_label?: string
    tone?: string
    speaking_style?: string
    interaction_style?: string
    self_description?: string
  }
  identity?: {
    agent_id?: string
    name?: string
    self_description?: string
    tone?: string
  }
  role_memory?: {
    primary_identity?: string
    long_term_goal?: string
    strengths?: string[]
    shortcomings?: string[]
    preferred_domains?: string[]
  }
  growth_state?: {
    phase?: string
    current_focus?: string
    blocked_reason?: string | null
    next_goal?: string
    last_reflection_at?: string | null
    last_commercial_settled_at?: string | null
    commercial_settled_count?: number
    commercial_settled_revenue?: number
    last_commercial_intake_id?: string | null
    pending_git_export?: boolean
    pending_git_export_reason?: string | null
    last_git_export_at?: string | null
    last_git_export_status?: string | null
    last_git_export_path?: string | null
    last_git_export_root?: string | null
  }
  operating_contract?: {
    autonomy_mode?: string
    learning_strategy?: string
    allow_external_learning?: boolean
    allow_shared_knowledge?: boolean
    must_record_experience?: boolean
  }
  onboarding?: {
    created_by_member_id?: string
    training_owner_member_id?: string
    status?: string
    created_at?: string | null
    notes?: string | null
    cloned_from_member_id?: string | null
    clone_mode?: string | null
  }
  organization?: {
    department_id?: string | null
    department_label?: string | null
  }
  content_profile?: {
    content_direction?: string | null
  }
  coaching_stats?: {
    total_records?: number
    last_record_at?: string | null
    last_coached_member_id?: string | null
    last_event_type?: string | null
  }
  training_plan?: {
    stage?: string
    owner_member_id?: string
    goals?: string[]
    curriculum?: string[]
    milestones?: string[]
    next_action?: string
    review_after?: string | null
  }
  experience_journal?: {
    last_compiled_at?: string | null
    latest_card_id?: string | null
    card_count?: number
    cards?: Array<{
      card_id?: string | null
      role?: string | null
      job_id?: string | null
      stage?: string | null
      status?: string | null
      title?: string | null
      summary?: string | null
      current_pattern?: string | null
      professional_risk?: string | null
      next_experiment?: string | null
      signature?: string | null
      source?: string | null
      learning_task_id?: string | null
      evidence?: string[]
      source_reflections?: string[]
      created_at?: string | null
      updated_at?: string | null
    }>
  }
  memory_hub?: MemberMemoryHubRuntime
  decision_state?: MemberMemoryHubDecisionState
  retrieval_state?: MemberMemoryHubRetrievalState
  active_case_id?: string | null
  last_decision_snapshot?: MemberMemoryHubSnapshot
  decision_history?: MemberMemoryHubSnapshot[]
  training_autopilot?: {
    auto_updated?: boolean
    reason?: string
    applied_rules?: string[]
    observations?: string[]
    coaching_view?: {
      growth_diagnosis?: string
      training_suggestion?: string
      trend_watch?: string
    }
  }
  professional_view?: {
    owner?: string
    summary?: string
    current_judgement?: string
    next_professional_focus?: string
    evidence?: string[]
    recent_reflections?: string[]
    reflection_summary?: string
    current_pattern?: string
    professional_risk?: string
    next_experiment?: string
  }
  training_overview?: {
    assigned_children_count?: number
    stage_counts?: Record<string, number>
    next_target?: {
      member_id?: string
      name?: string
      primary_role?: string
      stage?: string
      next_action?: string
    } | null
    owned_member_ids?: string[]
  }
  self_development?: {
    level?: string
    focus?: string[]
    current_objective?: string
    next_milestone?: string
    growth_signals?: string[]
    missing_capabilities?: string[]
  } | null
  current_jobs?: ChildMemberRuntimeJob[]
  world_observation?: {
    last_signal?: string | null
    blocked_by?: string[]
    active_feedback_channels?: string[]
  }
  derived_state?: {
    active_job_id?: string | null
    active_job_title?: string | null
    status?: string
    blocked_reason?: string | null
    next_action?: string | null
    signals?: string[]
  }
}

export interface AutonomyFormalTaskIntegrationPending {
  collaboration_request_id?: string
  phase?: string
  updated_at?: string | null
  provider_member_id?: string | null
  provider_task_id?: string | null
}

export interface AutonomyFormalTask {
  task_id?: string | null
  member_id?: string | null
  assigned_by_member_id?: string
  title?: string | null
  objective?: string | null
  deliverables?: string[]
  status?: string
  assigned_at?: string | null
  started_at?: string | null
  submitted_at?: string | null
  approved_at?: string | null
  result_summary?: string | null
  reflection?: string | null
  review_note?: string | null
  integration_pending?: AutonomyFormalTaskIntegrationPending | null
  work_node_archive?: {
    status?: string
    reason?: string | null
    gitee_path?: string
    local_root?: string
    target_repo?: string
    target_url?: string
    files?: string[]
    verified_files?: string[]
    remote_uploaded_files?: string[]
    integrity_verified?: boolean
    archived_at?: string
    next_action?: string
  } | null
  metadata?: Record<string, unknown>
}

export interface AutonomyFormalTaskRecommendation {
  recommendation_id?: string | null
  member_id?: string | null
  source_task_id?: string | null
  title?: string | null
  objective?: string | null
  deliverables?: string[]
  reason?: string | null
  status?: string
  created_at?: string | null
  adopted_at?: string | null
  metadata?: Record<string, unknown>
}

export interface AutonomyStatus {
  tenant_id?: string | null
  enabled: boolean
  domain: string
  status: string
  loop_interval_seconds: number
  last_run_at?: string | null
  last_error?: string | null
  samples?: Record<string, Record<string, {
    bundle_path?: string
    sample_signature?: string
    last_seen_at?: string
    submitted?: Array<{ task_type: string; task_id: string }>
    diagnosis?: {
      research_state?: string
      next_action?: string
      stable?: boolean
      analyze?: {
        task_id?: string
        status?: string
        evaluation_verdict?: string
        evaluation_score?: number | null
        strategy_reasons?: string[]
        strategy_runtime_adjustments?: Record<string, unknown>
      }
      reconstruct?: {
        task_id?: string
        status?: string
        evaluation_verdict?: string
        evaluation_score?: number | null
        issue_category?: string
        recommended_actions?: string[]
        strategy_reasons?: string[]
        strategy_runtime_adjustments?: Record<string, unknown>
      }
      learning_plan?: {
        needs_external_learning?: boolean
        policy?: TenantExternalLearningPolicy
        preferred_sources?: string[]
        validation_gate?: string
        queries?: string[]
      }
      learning_task?: LearningTask | null
    }
  }>>
  parent_profile?: {
    display_name?: string
    role_label?: string
    relationship_to_child?: string
    description?: string
  }
  training_review?: {
    last_review_at?: string | null
    last_trigger?: string
    changed_count?: number
    changed_members?: Array<{
      member_id?: string
      name?: string
      primary_role?: string
      training_stage?: string
      next_action?: string
    }>
    last_message?: string | null
  }
  relationship_center?: {
    last_delivery_at?: string | null
    parent_inbox?: Array<{
      message_id?: string
      sender_member_id?: string
      sender_role?: string
      message_type?: string
      title?: string
      content?: string
      created_at?: string
      metadata?: Record<string, unknown>
    }>
    conversation_threads?: Array<{
      thread_id?: string | null
      participants?: string[]
      messages?: Array<{
        message_id?: string
        sender_member_id?: string
        sender_role?: string
        message_type?: string
        content?: string
        created_at?: string
        metadata?: Record<string, unknown>
      }>
    }>
  }
  task_center?: {
    items?: AutonomyFormalTask[]
    recommendations?: AutonomyFormalTaskRecommendation[]
  }
  intake_center?: {
    items?: Array<Record<string, unknown>>
    events?: Array<Record<string, unknown>>
  }
  intake_funnel?: {
    counts?: Record<string, number>
    open_count?: number
    pipeline_value?: number
    settled_value?: number
    currency?: string
    item_count?: number
  }
  child_members?: {
    selected_member_id?: string
    items?: ChildMemberRuntimeProfile[]
  }
  primary_child_member_id?: string
  child_agent?: {
    identity?: {
      agent_id?: string
      name?: string
      self_description?: string
      tone?: string
    }
    role_memory?: {
      primary_identity?: string
      long_term_goal?: string
      strengths?: string[]
      preferred_domains?: string[]
    }
    growth_state?: {
      phase?: string
      current_focus?: string
      blocked_reason?: string | null
      next_goal?: string
      last_reflection_at?: string | null
    }
    training_plan?: {
      stage?: string
      owner_member_id?: string
      goals?: string[]
      curriculum?: string[]
      milestones?: string[]
      next_action?: string
      review_after?: string | null
    }
    experience_journal?: {
      last_compiled_at?: string | null
      latest_card_id?: string | null
      cards?: Array<{
        card_id?: string | null
        role?: string | null
        job_id?: string | null
        stage?: string | null
        status?: string | null
        title?: string | null
        summary?: string | null
        current_pattern?: string | null
        professional_risk?: string | null
        next_experiment?: string | null
        signature?: string | null
        evidence?: string[]
        source_reflections?: string[]
        created_at?: string | null
        updated_at?: string | null
      }>
    }
    training_autopilot?: {
      auto_updated?: boolean
      reason?: string
      applied_rules?: string[]
      observations?: string[]
      coaching_view?: {
        growth_diagnosis?: string
        training_suggestion?: string
        trend_watch?: string
      }
    }
    professional_view?: {
      owner?: string
      summary?: string
      current_judgement?: string
      next_professional_focus?: string
      evidence?: string[]
      recent_reflections?: string[]
      reflection_summary?: string
      current_pattern?: string
      professional_risk?: string
      next_experiment?: string
    }
    training_overview?: {
      assigned_children_count?: number
      stage_counts?: Record<string, number>
      next_target?: {
        member_id?: string
        name?: string
        primary_role?: string
        stage?: string
        next_action?: string
      } | null
      owned_member_ids?: string[]
    }
    self_development?: {
      level?: string
      focus?: string[]
      current_objective?: string
      next_milestone?: string
      growth_signals?: string[]
      missing_capabilities?: string[]
    } | null
    current_jobs?: ChildMemberRuntimeJob[]
    world_observation?: {
      last_signal?: string | null
      blocked_by?: string[]
      active_feedback_channels?: string[]
    }
    derived_state?: {
      active_job_id?: string | null
      active_job_title?: string | null
      status?: string
      blocked_reason?: string | null
      next_action?: string | null
      signals?: string[]
    }
  }
}

export interface TrainingReviewSummary {
  saved?: boolean
  changed_count?: number
  changed_members?: Array<{
    member_id?: string
    name?: string
    primary_role?: string
    training_stage?: string
    next_action?: string
  }>
}

export interface MemoryHubStatusPayload {
  tenant_id?: string
  member_id?: string | null
  memory_hub?: MemberMemoryHubRuntime | null
  last_decision_snapshot?: MemberMemoryHubSnapshot | null
  decision_history?: MemberMemoryHubSnapshot[]
}

export interface WorkerManifest {
  worker_id: string
  title: string
  capability_type: string
  work_type_ids: string[]
  task_types: string[]
  owned_modules: string[]
  default_enabled: boolean
  source?: string
  definition_path?: string
}

export interface WorkerRegistryConfigItem {
  enabled: boolean
  title?: string
  capability_type?: string
  task_types?: string[]
  work_type_ids?: string[]
  owned_modules?: string[]
}

export interface WorkerRuntimeItem extends WorkerManifest {
  enabled: boolean
  handler_count: number
  task_types: string[]
}

export interface WorkerRegistryPayload {
  manifests: Record<string, WorkerManifest>
  config: {
    updated_at?: string
    workers: Record<string, WorkerRegistryConfigItem>
  }
  runtime: {
    updated_at?: string
    workers: Record<string, WorkerRuntimeItem>
    available_workers: Record<string, WorkerRegistryConfigItem>
  }
  self_media?: {
    executor_registry?: SelfMediaExecutorRegistry
  }
}

export interface SelfMediaExecutorRegistry {
  preferred_mode?: string
  configured_runtime?: {
    preferred_mode?: string
    executor_dir?: string | null
    executor_name?: string
    executor_adapter?: string | null
    login_target_url?: string | null
  }
  selected?: {
    key?: string
    label?: string
    adapter?: string
    source?: string
    root_dir?: string
    available?: boolean
  }
  executors?: Array<{
    key?: string
    label?: string
    adapter?: string
    source?: string
    root_dir?: string
    available?: boolean
  }>
}

export interface SelfMediaExecutorConfigPayload {
  self_media?: {
    executor?: {
      preferred_mode?: string
      executor_dir?: string | null
      executor_name?: string
      executor_adapter?: string | null
      login_target_url?: string | null
    }
  }
  executor_registry?: SelfMediaExecutorRegistry
}

export interface BrainOverview {
  tenant_id: string
  summary: {
    workers_total: number
    workers_enabled: number
    mission_runs_total: number
    mission_running: number
    learning_tasks_total: number
    learning_pending: number
    review_queue_total: number
    platform_promotions_total: number
    autonomy_enabled: boolean
    autonomy_status?: string
  }
  autonomy?: AutonomyStatus
  workers: Array<{
    worker_id: string
    title: string
    enabled: boolean
    handler_count: number
    capability_type?: string
  }>
  recent_mission_runs: Array<{
    mission_run_id?: string
    title?: string
    goal?: string
    status?: string
    mission_kind?: string
    updated_at?: string
    autonomy_session_id?: string
  }>
  recent_learning_tasks: Array<{
    task_id?: string
    title?: string
    status?: string
    issue_category?: string
    updated_at?: string
  }>
  recent_reviews: Array<{
    id?: string
    strategy_id?: string
    status?: string
    reason?: string
    alert_reason?: string
    updated_at?: string
  }>
  platform_promotions: Array<{
    id?: string
    strategy_id?: string
    promoted_at?: string
    title?: string
    summary?: string
  }>
  evolution_summary?: Record<string, unknown>
}

export function listPlugins() {
  return get<{ plugins: PluginItem[]; skipped: string[] }>('/api/plugins')
}

export function getTenantPluginPolicy(tenantId: string) {
  return get<{ tenant_id: string; policy: TenantPluginPolicy }>(`/api/tenants/${tenantId}/plugins`)
}

export function updateTenantPluginPolicy(
  tenantId: string,
  policy: TenantPluginPolicy
) {
  return put<{ tenant_id: string; policy: TenantPluginPolicy }>(
    `/api/tenants/${tenantId}/plugins`,
    policy
  )
}

export function getTenantKnowledgePolicy(tenantId: string) {
  return get<{ tenant_id: string; policy: TenantKnowledgePolicy }>(`/api/tenants/${tenantId}/knowledge-policy`)
}

export function getTenantExternalLearningPolicy(tenantId: string) {
  return get<{ tenant_id: string; policy: TenantExternalLearningPolicy }>(`/api/tenants/${tenantId}/external-learning-policy`)
}

export function updateTenantKnowledgePolicy(
  tenantId: string,
  policy: TenantKnowledgePolicy
) {
  return put<{ tenant_id: string; policy: TenantKnowledgePolicy }>(
    `/api/tenants/${tenantId}/knowledge-policy`,
    policy
  )
}

export function updateTenantExternalLearningPolicy(
  tenantId: string,
  policy: TenantExternalLearningPolicy
) {
  return put<{ tenant_id: string; policy: TenantExternalLearningPolicy }>(
    `/api/tenants/${tenantId}/external-learning-policy`,
    policy
  )
}

export function getPlatformSharedSeeds(tenantId: string, limit = 5) {
  return get<{
    tenant_id: string
    is_cold_start: boolean
    current_override_count: number
    items: PlatformSharedSeedItem[]
  }>(`/api/tenants/${tenantId}/platform-shared/seeds?limit=${encodeURIComponent(String(limit))}`)
}

export function applyPlatformSharedSeeds(tenantId: string, strategyIds: string[]) {
  return post<{
    tenant_id: string
    applied: Array<{
      strategy_id: string
      weight_delta: number
      preferred: boolean
      source_tenant_id?: string
    }>
    count: number
    strategy_overrides: Record<string, unknown>
  }>(`/api/tenants/${tenantId}/platform-shared/seeds/apply`, {
    strategy_ids: strategyIds,
  })
}

export function getAutonomyStatus(tenantId = 'default') {
  return get<AutonomyStatus>(`/api/autonomy/status?tenant_id=${encodeURIComponent(tenantId)}`)
}

export function getAutonomyMemoryHubStatus(payload: {
  tenant_id?: string
  member_id?: string
}) {
  const params = new URLSearchParams()
  params.set('tenant_id', payload.tenant_id || 'default')
  if (payload.member_id) params.set('member_id', payload.member_id)
  return get<MemoryHubStatusPayload>(`/api/autonomy/memory-hub/status?${params.toString()}`)
}

export function runAutonomyMemoryHub(payload: {
  tenant_id?: string
  member_id: string
  trigger?: string
}) {
  return post<{
    autonomy?: AutonomyStatus
    memory_hub?: MemberMemoryHubRuntime | null
    last_decision_snapshot?: MemberMemoryHubSnapshot | null
  }>('/api/autonomy/memory-hub/run', payload)
}

export function replayAutonomyMemoryHub(payload: {
  tenant_id?: string
  member_id: string
  case_id: string
}) {
  return post<{
    tenant_id?: string
    member_id?: string
    snapshot?: MemberMemoryHubSnapshot | null
  }>('/api/autonomy/memory-hub/replay', payload)
}

export function updateAutonomyIdentity(payload: {
  tenant_id?: string
  parent_profile?: Record<string, unknown>
  child_agent?: Record<string, unknown>
  primary_child_member_id?: string
  child_members?: {
    selected_member_id?: string
    items?: Record<string, unknown>[]
  }
}) {
  return put<AutonomyStatus>('/api/autonomy/identity', payload)
}

export function createAutonomyMember(payload: {
  tenant_id?: string
  name: string
  role_label?: string
  role_key?: string
  primary_role?: string
  work_type_id?: string
  self_description?: string
  long_term_goal?: string
  trainer_member_id?: string
  created_by_member_id?: string
}) {
  return post<{
    employee?: ChildMemberRuntimeProfile
    member?: ChildMemberRuntimeProfile
    autonomy?: AutonomyStatus
  }>('/api/autonomy/members', payload)
}

export function createAutonomyEmployee(payload: {
  tenant_id?: string
  name: string
  role_label?: string
  role_key?: string
  primary_role?: string
  work_type_id?: string
  self_description?: string
  long_term_goal?: string
  trainer_member_id?: string
  created_by_member_id?: string
}) {
  return createAutonomyMember(payload)
}

export function cloneAutonomyMember(payload: {
  tenant_id?: string
  source_member_id: string
  name: string
  account_id: string
  content_direction: string
  clone_mode?: 'account_variant'
  prefill_first_task?: boolean
  trainer_member_id?: string
}) {
  return post<{
    employee?: ChildMemberRuntimeProfile
    member?: ChildMemberRuntimeProfile
    clone?: {
      clone_mode?: string
      source_member_id?: string
      prefill_first_task?: boolean
      recommendation?: AutonomyFormalTaskRecommendation
    }
    autonomy?: AutonomyStatus
  }>('/api/autonomy/members/clone', payload)
}

export type CollaborationRequest = {
  request_id?: string
  requester_member_id?: string
  requester_task_id?: string | null
  needed_capability?: string
  target_work_type_id?: string | null
  target_department_id?: string | null
  title?: string
  description?: string | null
  status?: string
  requester_continues?: boolean
  assignment?: Record<string, unknown> | null
}

export function getCollaborationPolicies() {
  return get<Record<string, unknown>>('/api/autonomy/collaborations/policies')
}

export function listCollaborations(params: {
  tenant_id?: string
  role?: 'orchestrator' | 'requester' | 'provider'
  member_id?: string
}) {
  const query = new URLSearchParams()
  if (params.tenant_id) query.set('tenant_id', params.tenant_id)
  if (params.role) query.set('role', params.role)
  if (params.member_id) query.set('member_id', params.member_id)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return get<{ items?: CollaborationRequest[]; collaboration_center?: Record<string, unknown> }>(
    `/api/autonomy/collaborations${suffix}`,
  )
}

export function createCollaborationRequest(payload: {
  tenant_id?: string
  requester_member_id: string
  needed_capability: string
  title: string
  description?: string
  requester_task_id?: string
  target_work_type_id?: string
  target_department_id?: string
  requester_continues?: boolean
  policy_id?: string
}) {
  return post<{ request?: CollaborationRequest; autonomy?: AutonomyStatus }>('/api/autonomy/collaborations', payload)
}

export function assignCollaborationRequest(
  requestId: string,
  payload: {
    tenant_id?: string
    provider_member_id: string
    provider_task_id?: string
    assigned_by?: string
  },
) {
  return post<{ request?: CollaborationRequest; assignment?: Record<string, unknown>; autonomy?: AutonomyStatus }>(
    `/api/autonomy/collaborations/${encodeURIComponent(requestId)}/assign`,
    payload,
  )
}

export function markCollaborationIntegrated(
  requestId: string,
  payload: { tenant_id?: string; member_id: string },
) {
  return post<{ request?: CollaborationRequest; autonomy?: AutonomyStatus }>(
    `/api/autonomy/collaborations/${encodeURIComponent(requestId)}/mark-integrated`,
    payload,
  )
}

export function runAutonomyTrainingReview(tenantId = 'default') {
  return post<{
    autonomy?: AutonomyStatus
    review_summary?: TrainingReviewSummary
  }>('/api/autonomy/training-review', { tenant_id: tenantId })
}

export function postParentRelationshipMessage(payload: {
  tenant_id?: string
  target_member_id: string
  content: string
  title?: string
  metadata?: Record<string, unknown>
}) {
  return post<AutonomyStatus>('/api/autonomy/relationship/parent-message', payload)
}

export function postChildRelationshipReply(payload: {
  tenant_id?: string
  member_id: string
  content: string
}) {
  return post<AutonomyStatus>('/api/autonomy/relationship/child-reply', payload)
}

export function postTrainerRelationshipAction(payload: {
  tenant_id?: string
  member_id: string
  content: string
  action_type?: string
  title?: string
  metadata?: Record<string, unknown>
}) {
  return post<AutonomyStatus>('/api/autonomy/relationship/trainer-action', payload)
}

export function assignAutonomyTask(payload: {
  tenant_id?: string
  member_id: string
  title: string
  objective: string
  recommendation_id?: string
  deliverables?: string[]
  metadata?: Record<string, unknown>
}) {
  return post<{
    autonomy?: AutonomyStatus
    task?: AutonomyFormalTask
  }>('/api/autonomy/tasks/assign', payload)
}

export function submitAutonomyTask(payload: {
  tenant_id?: string
  task_id: string
  result_summary: string
  reflection: string
}) {
  return post<{
    autonomy?: AutonomyStatus
    task?: AutonomyFormalTask
  }>('/api/autonomy/tasks/submit', payload)
}

export function approveAutonomyTask(payload: {
  tenant_id?: string
  task_id: string
  review_note?: string
}) {
  return post<{
    autonomy?: AutonomyStatus
    task?: AutonomyFormalTask
    evolution_summary?: Record<string, unknown>
    review_summary?: Record<string, unknown>
  }>('/api/autonomy/tasks/approve', payload)
}

export function getBrainOverview(tenantId: string) {
  return get<BrainOverview>(`/api/autonomy/brain-overview?tenant_id=${encodeURIComponent(tenantId)}`)
}

export function getWorkerRegistry() {
  return get<WorkerRegistryPayload>('/api/workers/registry')
}

export function updateWorkerRegistry(workers: Record<string, { enabled: boolean }>) {
  return put<{
    updated_at?: string
    workers: Record<string, WorkerRegistryConfigItem>
  }>('/api/workers/registry', { workers })
}

export function updateSelfMediaExecutorConfig(payload: {
  preferred_mode: string
  executor_dir?: string | null
  executor_name?: string
  executor_adapter?: string | null
  login_target_url?: string | null
}) {
  return put<SelfMediaExecutorConfigPayload>('/api/self-media/executor', payload)
}

export function getAutonomyLearningTasks(tenantId?: string, status?: string) {
  const params = new URLSearchParams()
  if (tenantId) params.set('tenant_id', tenantId)
  if (status) params.set('status', status)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return get<{ updated_at?: string; items: LearningTask[] }>(`/api/autonomy/learning-tasks${suffix}`)
}

export function getEvolutionOverview(tenantId: string) {
  return get<EvolutionOverview>(`/api/evolution/overview?tenant_id=${encodeURIComponent(tenantId)}`)
}

export function validateLearningTask(taskId: string, tenantId: string) {
  return post<{
    mode: string
    review_id?: string
    status?: string
    task_type?: string
    source_task_id?: string
    source_task_ids?: string[]
    created_task_ids?: string[]
    message?: string
  }>(`/api/autonomy/learning-tasks/${encodeURIComponent(taskId)}/validate`, {
    tenant_id: tenantId,
  })
}
