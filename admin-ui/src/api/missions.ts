import { get, post, request } from './request'

export interface MissionTemplate {
  mission_kind: string
  title: string
  description?: string
  primary_capability_type?: string
  delivery_targets?: string[]
}

export interface MissionPlanNode {
  id: string
  title: string
  objective: string
  task_type: string
  capability_type: string
  acceptance: string
  status: string
  gap_type: string
  blockers: string[]
  learning_objectives: string[]
  validation_checks: string[]
  priority: string
  reasoning: string[]
  available_capability_ids: string[]
  knowledge_signals: {
    experience_count: number
    growth_event_count: number
    role_reflection_count?: number
    top_experience_ids: string[]
    verified_skill_count?: number
    top_verified_skill_ids?: string[]
    latest_role_reflection_id?: string | null
    latest_role_reflection_summary?: string | null
    latest_role_reflection_stage?: string | null
  }
  role_reflection_context?: {
    experience_id?: string
    member_id?: string
    member_name?: string
    primary_role?: string
    summary?: string
    stage?: string
    status?: string
    blocked_reason?: string
    next_experiment?: string
  }
  recommended_skill_ids?: string[]
  recommended_skills?: Array<{
    id: string
    name: string
    trust_level: string
    success_rate: number
    usage_count: number
    framework_hint?: string
    accepted_tasks?: string[]
  }>
  next_actions: string[]
  decision_trace?: Array<{
    step?: string
    rule_id?: string
    result?: string
    evidence?: Record<string, unknown>
  }>
}

export interface MissionPlan {
  tenant_id: string
  goal: string
  mission_kind: string
  title: string
  description?: string
  primary_capability_type?: string
  delivery_targets: string[]
  status_summary: {
    overall_status: string
    node_count: number
    counts: Record<string, number>
  }
  gap_summary: {
    total_nodes: number
    input_gap_count: number
    capability_gap_count: number
    experience_gap_count: number
    knowledge_gap_count: number
    reuse_existing_count: number
    high_priority_node_ids: string[]
    blockers: string[]
    enabled_packages: string[]
  }
  learning_task_ids?: string[]
  learning_tasks: Array<{
    task_id: string
    node_id: string
    title: string
    status: string
    priority: string
    gap_type: string
    capability_type: string
    blockers: string[]
    learning_objectives: string[]
    validation_checks: string[]
    recommended_skill_ids: string[]
    next_actions: string[]
    source_context?: {
      source_path?: string
      source_dir?: string
      work_type_id?: string
      role_reflection_context?: MissionPlanNode['role_reflection_context']
    }
  }>
  nodes: MissionPlanNode[]
  recommended_next_actions: string[]
}

export interface MissionRunAction {
  node_id: string
  title?: string
  action_type: string
  status: string
  detail?: string
  decision_trace?: Array<{
    step?: string
    rule_id?: string
    result?: string
    evidence?: Record<string, unknown>
  }>
  task_type?: string
  task_id?: string
  task_status?: string
  task_error?: string
  capability_type?: string
  linked_learning_task_id?: string
  next_actions?: string[]
  role_reflection_context?: MissionPlanNode['role_reflection_context']
  task_outcome?: string
  insight_summary?: string
  growth_update?: {
    experience_id?: string
    domain?: string
    task_type?: string
    quality_score?: number
    recorded_at?: string
  }
  promotion?: {
    experience_id?: string
    skill_candidate?: {
      skill_id?: string
      name?: string
      domain?: string
      trust_level?: string
      replay_eligible?: boolean
      replay_status?: string
      replay_reason?: string
    }
  }
  skill_id?: string
  validation_status?: string
  promotion_status?: string
  evidence_id?: string
  experience_id?: string
  execution_succeeded?: boolean
  task_result?: {
    validation_outcome?: string
    message?: string
    insight_summary?: string
    experience_id?: string
    analytics_type?: string
    next_actions?: string[]
    growth_update?: {
      experience_id?: string
      domain?: string
      task_type?: string
      quality_score?: number
      recorded_at?: string
    }
    analytics_summary?: {
      headline?: string
      insight_summary?: string
      recommendations?: string[]
    }
  }
}

export interface MissionStaffingRequest {
  request_id: string
  tenant_id: string
  mission_run_id: string
  node_id: string
  role_id?: string | null
  required_capabilities?: string[]
  task_type?: string | null
  risk_level?: string
  status?: string
}

export interface MissionStaffingEmployee {
  member_id: string
  name: string
  primary_role?: string
  status: string
  organization_worker_ids?: string[]
}

export interface MissionStaffingWorker {
  worker_id: string
  owner_member_id: string
  role_id: string
  handler_id: string
  status: string
  active_task_count: number
  available: boolean
  handler_matches: boolean
  compatible_node_ids: string[]
}

export interface MissionStaffingAssignment {
  node_id: string
  request_id: string
  employee_member_id: string
  worker_id: string
  status: string
  approved_by?: string
  approved_at?: string
}

export interface MissionStaffingOptions {
  mission_run_id: string
  tenant_id: string
  pending_requests: MissionStaffingRequest[]
  assignments: MissionStaffingAssignment[]
  employees: MissionStaffingEmployee[]
  workers: MissionStaffingWorker[]
}

export interface MissionRun {
  mission_run_id: string
  tenant_id: string
  goal: string
  mission_kind: string
  title?: string
  created_at: string
  status: string
  context: Record<string, unknown> & {
    member_id?: string
    member_name?: string
    member_primary_role?: string
    member_resolution_source?: string
    previous_mission_run_id?: string
    root_mission_run_id?: string
  }
  counts: Record<string, number>
  submitted_task_ids: string[]
  actions: MissionRunAction[]
  staffing_requests?: MissionStaffingRequest[]
  staffing_assignments?: MissionStaffingAssignment[]
  plan: MissionPlan
  member_reflection_member_id?: string
  summary?: {
    session?: {
      autonomy_session_id?: string
      run_index?: number
      run_count?: number
      root_mission_run_id?: string
      latest_mission_run_id?: string
    }
    worker_summary_type?: string
    worker_summary?: {
      domain?: string
      role_reflection?: {
        experience_id?: string
        member_id?: string
        member_name?: string
        primary_role?: string
        summary?: string
        stage?: string
        status?: string
        blocked_reason?: string
        next_experiment?: string
      }
      analyze?: {
        status?: string
        detail?: string
        summary?: string
        strategy_id?: string
        capability_id?: string
        evaluation_score?: number
      }
      reconstruct?: {
        status?: string
        detail?: string
        summary?: string
        strategy_id?: string
        capability_id?: string
        evaluation_verdict?: string
        evaluation_score?: number
        evaluation_metrics?: {
          components?: number
          has_target_dir?: boolean
        }
      }
      validation?: {
        verdict?: string
        components?: number
        has_target_dir?: boolean
        framework_summary?: string
        reconstruct_summary?: string
        evaluation_score?: number
      }
      promotion?: {
        experience_id?: string
        domain?: string
        task_type?: string
        quality_score?: number
        promoted_at?: string
        platform_promotion_status?: {
          status?: string
          reason?: string
        }
      }
      channel?: string
      connector?: {
        status?: string
        account?: string
        username?: string
        logged_in?: boolean
        message?: string
        executor_name?: string
        executor_adapter?: string
        executor_root_dir?: string
      }
      draft?: {
        status?: string
        topic?: string
        publish_content_type?: string
        article_title?: string
        preview?: string
        message?: string
        experience_id?: string
        executor_name?: string
        executor_adapter?: string
        executor_root_dir?: string
        draft_path?: string
        article_path?: string
      }
      analytics?: Array<{
        analytics_type?: string
        headline?: string
        insight_summary?: string
        recommendations?: string[]
        experience_id?: string
      }>
      feedback?: {
        headline?: string
        insight_summary?: string
        selected_feedback?: Array<{
          feedback_text?: string
          category?: string
        }>
        recommended_actions?: string[]
        experience_id?: string
      }
      growth_updates?: Array<{
        experience_id?: string
        domain?: string
        task_type?: string
        quality_score?: number
        recorded_at?: string
      }>
      recommended_next_actions?: string[]
    }
    next_cycle_plan?: {
      title?: string
      status?: string
      goal?: string
      focus_points?: string[]
      next_steps?: string[]
      preferred_content_mode?: string
      feedback_goal_hint?: string
      role_reflection_experiments?: string[]
      role_reflection_summaries?: string[]
    }
    growth_timeline?: Array<{
      timestamp: string
      event_type: string
      title: string
      detail?: string
      experience_id?: string
    }>
  }
  auto_continue_status?: string
  auto_continue_triggered_at?: string
  auto_continue_triggered_run_id?: string
  auto_continue_source_mission_run_id?: string
}

export function listMissionTemplates() {
  return get<{ items: MissionTemplate[] }>('/api/missions/templates')
}

export function planMission(body: {
  tenant_id?: string
  goal: string
  mission_kind?: string
  context?: Record<string, unknown>
}) {
  return post<MissionPlan>('/api/missions/plan', body)
}

export function executeMission(body: {
  tenant_id?: string
  goal: string
  mission_kind?: string
  context?: Record<string, unknown>
}) {
  return post<MissionRun>('/api/missions/execute', body)
}

export function listMissionRuns(tenantId?: string, limit = 20) {
  const query = new URLSearchParams()
  if (tenantId) query.set('tenant_id', tenantId)
  query.set('limit', String(limit))
  return get<{ updated_at?: string; items: MissionRun[] }>(`/api/missions/runs?${query.toString()}`)
}

export function getMissionRun(missionRunId: string) {
  return get<MissionRun>(`/api/missions/${encodeURIComponent(missionRunId)}`)
}

export function getMissionStaffingOptions(missionRunId: string, tenantId: string) {
  const query = new URLSearchParams({ tenant_id: tenantId })
  return get<MissionStaffingOptions>(
    `/api/missions/${encodeURIComponent(missionRunId)}/staffing-options?${query.toString()}`
  )
}

export function approveMissionStaffing(
  missionRunId: string,
  payload: {
    tenant_id: string
    node_id: string
    employee_member_id: string
    worker_id: string
  }
) {
  return post<Record<string, unknown>>(
    `/api/missions/${encodeURIComponent(missionRunId)}/staffing-assignments`,
    payload
  )
}

export interface MissionSkillReplayRecoveryItem {
  mission_run_id: string
  tenant_id: string
  goal?: string
  node_id: string
  task_id: string
  skill_id: string
  title?: string
  recovery_status?: string
  recovery_reason?: string
  interrupted_at?: string
  candidate_binding_status: string
  skill_binding?: {
    skill_id: string
    skill_version: string
    content_sha256: string
    trust_level: string
  } | null
  stage_request_id?: string | null
  execution_request_id?: string | null
  validation_request_id?: string | null
  promotion_request_id?: string | null
  broker_status: Record<string, { status?: string; error_type?: string }>
  validator_status: { status?: string; error_type?: string }
  verified_receipts: {
    broker_stage?: string
    broker_execution?: string
    validator?: string
    broker_promotion?: string
    execution_succeeded?: boolean | null
    validation_id?: string | null
  }
  recovery_assessment: {
    status: string
    automatic_resume: boolean
    next_step: string
  }
  evidence_ref?: {
    evidence_id?: string
    sha256?: string
    relative_path?: string
  } | null
}

export function listMissionSkillReplayRecoveryReviews(tenantId: string, limit = 100) {
  const query = new URLSearchParams({ tenant_id: tenantId, limit: String(limit) })
  return get<{ count: number; items: MissionSkillReplayRecoveryItem[] }>(
    `/api/missions/skill-replays/recovery-review?${query.toString()}`
  )
}

export function resumeMissionSkillReplayPromotion(
  missionRunId: string,
  skillId: string,
  taskId: string
) {
  return post<Record<string, unknown>>(
    `/api/missions/${encodeURIComponent(missionRunId)}/skills/${encodeURIComponent(skillId)}/recovery/${encodeURIComponent(taskId)}/resume-promotion`,
    { confirm: true }
  )
}

export function continueMission(missionRunId: string) {
  return post<{ source_mission_run_id: string; continued_mission_run: MissionRun }>(
    `/api/missions/${encodeURIComponent(missionRunId)}/continue`,
    {}
  )
}

/**
 * Replay a verified Skill for one Mission node.
 *
 * The caller must create one UUID per intentional Replay attempt and retain it
 * while retrying that same HTTP request. A new UUID means a new attempt.
 */
export function reusePublishedMissionSkill(
  missionRunId: string,
  skillId: string,
  nodeId: string,
  binding: { schema_version: string; skill_id: string; skill_version: string; content_sha256: string; trust_level: string },
  idempotencyKey: string,
) {
  if (!idempotencyKey.trim()) throw new Error('Published Skill reuse requires a stable Idempotency-Key')
  return request<Record<string, unknown>>(
    `/api/missions/${encodeURIComponent(missionRunId)}/skills/${encodeURIComponent(skillId)}/reuse-published`,
    { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey }, body: JSON.stringify({ node_id: nodeId, skill_binding: binding }) }
  )
}

export function replayMissionSkill(
  missionRunId: string,
  skillId: string,
  nodeId: string,
  idempotencyKey: string
) {
  if (!idempotencyKey.trim()) {
    throw new Error('Replay requires a stable Idempotency-Key')
  }
  return request<Record<string, unknown>>(
    `/api/missions/${encodeURIComponent(missionRunId)}/skills/${encodeURIComponent(skillId)}/replay`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify({ node_id: nodeId }),
    }
  )
}
