import { get, post, put } from './request'

export type FinanceSummary = {
  project_id: string
  channel: string
  period: string
  revenue: number
  cost: number
  views: number
  likes: number
  comments: number
  net: number
  verdict: 'profitable' | 'break_even' | 'loss' | 'unknown' | string
  updated_at?: string
  source?: string
  headline?: string
  is_latest_period?: boolean
}

export type FinanceDecision = {
  id: string
  project_id: string
  period: string
  action: 'continue_invest' | 'shrink' | 'adjust_strategy' | string
  note?: string
  verdict?: string
  net?: number
  revenue?: number
  cost?: number
  created_at?: string
}

export type FinanceOverview = {
  project_ids: string[]
  items: FinanceSummary[]
  primary: FinanceSummary
  total: number
  decisions?: FinanceDecision[]
  latest_decision?: FinanceDecision | null
  trends?: FinanceSummary[]
  commercial_verdict?: CommercialVerdict | null
}

export type CommercialVerdict = {
  headline: string
  recommendation: 'continue_invest' | 'shrink' | 'adjust_strategy' | 'wait_for_data' | string
  recommendation_label: string
  confidence: 'low' | 'medium' | 'high' | string
  reasons: string[]
  next_actions: string[]
  score: number
  primary_verdict?: string
  primary_net?: number
}

export type CommercialReadinessStep = {
  key: string
  label: string
  done: boolean
  hint?: string
  route?: string
}

export type CommercialReadiness = {
  score: number
  stage: 'setup' | 'operating' | 'monetizing' | string
  stage_label: string
  steps: CommercialReadinessStep[]
  met_count: number
  total_steps: number
  blockers: string[]
  next_step?: CommercialReadinessStep | null
  enabled_workers?: string[]
  work_type_count?: number
  member_count?: number
}

export function getFinanceOverview(period?: string) {
  const query = new URLSearchParams()
  if (period) query.set('period', period)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return get<FinanceOverview>(`/api/finance/overview${suffix}`)
}

export function getFinanceSummary(projectId?: string, period?: string) {
  const query = new URLSearchParams()
  if (projectId) query.set('project_id', projectId)
  if (period) query.set('period', period)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return get<FinanceSummary>(`/api/finance/summary${suffix}`)
}

export function updateFinanceCost(projectId: string, cost: number, period?: string, channel?: string) {
  return put<FinanceSummary>('/api/finance/cost', {
    project_id: projectId,
    cost,
    period,
    channel: channel || 'toutiao',
  })
}

export function recordFinanceDecision(
  projectId: string,
  action: FinanceDecision['action'],
  note?: string,
  period?: string,
) {
  return post<FinanceDecision>('/api/finance/decision', {
    project_id: projectId,
    action,
    note,
    period,
  })
}

export function getCommercialReadiness(tenantId?: string) {
  const query = new URLSearchParams()
  if (tenantId) query.set('tenant_id', tenantId)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return get<CommercialReadiness>(`/api/commercial/readiness${suffix}`)
}

export type WeeklyBriefing = {
  period_label: string
  generated_at?: string
  headline: string
  bullets: string[]
  next_actions: string[]
  finance_verdict?: CommercialVerdict | null
  readiness_score: number
  readiness_stage: string
  operations: {
    members: number
    work_types: number
    tasks_approved: number
    tasks_submitted: number
    knowledge_learning_active: number
    training_reviews: number
  }
}

export function getWeeklyBriefing(tenantId?: string) {
  const query = new URLSearchParams()
  if (tenantId) query.set('tenant_id', tenantId)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return get<WeeklyBriefing>(`/api/commercial/weekly-briefing${suffix}`)
}
