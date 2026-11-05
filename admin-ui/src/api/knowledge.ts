import { get, post } from './request'
import type { GitKnowledgeConfig, KnowledgeContainer } from './git'
import type { KnowledgeLayerAdvice } from './evolution'

export interface KnowledgeSkill {
  id?: string
  name: string
  domain?: string
  capability_type?: string
  trust_level?: string
  source?: string
  path?: string
  description?: string
  usage_count?: number
  success_rate?: number
  created_at?: string
  updated_at?: string
  provenance?: {
    mission_run_id?: string
    mission_node_id?: string
    mission_kind?: string
    primary_worker_id?: string
    worker_id?: string
    evidence_ids?: string[]
    validation_evidence?: Record<string, unknown>
  }
  parameters?: Record<string, unknown>
}

export interface KnowledgeSkillsPayload {
  tenant_id: string
  repo: string
  repo_full_name: string
  git_knowledge?: GitKnowledgeConfig
  knowledge_containers?: KnowledgeContainer[]
  knowledge_layer_advice?: KnowledgeLayerAdvice
  autonomy_skill_summary?: {
    auto_generated_total: number
    auto_draft_count: number
    auto_verified_count: number
  }
  recent_autonomy_skills?: KnowledgeSkill[]
  skills: KnowledgeSkill[]
}

export interface KnowledgeShard {
  repository_id: string
  domain: string
  provider: string
  status: string
  writable: boolean
  full_name?: string
  url?: string
  branch?: string
  capacity_ratio?: number
  capacity_warning?: boolean
  usage?: {
    used_bytes?: number
    file_count?: number
    largest_file_bytes?: number
    measured_at?: number
  }
}

export interface KnowledgeShardInventory {
  tenant_id: string
  shards: KnowledgeShard[]
  total: number
  domains: Record<string, {
    total: number
    active: number
    sealed: number
    provisioning: number
  }>
  registry_path: string
}

export function getKnowledgeShards(tenantId: string) {
  return get<KnowledgeShardInventory>(
    `/api/tenants/${encodeURIComponent(tenantId)}/knowledge-shards`
  )
}

export function getKnowledgeSkills(tenantId: string) {
  return get<KnowledgeSkillsPayload>(`/api/knowledge/skills?tenant_id=${encodeURIComponent(tenantId)}`)
}

export function getKnowledgeSkillDetail(tenantId: string, domain: string, skillName: string) {
  return get<KnowledgeSkill>(
    `/api/knowledge/skills/${encodeURIComponent(domain)}/${encodeURIComponent(skillName)}?tenant_id=${encodeURIComponent(tenantId)}`
  )
}

export function syncLocalSkills(tenantId: string) {
  return post<{
    tenant_id: string
    count: number
    repo: string
    uploaded: Array<Record<string, string>>
  }>('/api/knowledge/sync-local-skills', {
    tenant_id: tenantId,
  })
}

export function exportTenantExperiences(tenantId: string) {
  return post<{
    tenant_id: string
    repo: string
    file_path: string
    journal_summary?: {
      member_count?: number
      card_total?: number
      latest_compiled_at?: string | null
    }
  }>(`/api/tenants/${encodeURIComponent(tenantId)}/git-knowledge/export/experiences`, {})
}

export function exportTenantReport(tenantId: string) {
  return post<{
    tenant_id: string
    repo: string
    file_path: string
  }>(`/api/tenants/${encodeURIComponent(tenantId)}/git-knowledge/export/report`, {})
}
