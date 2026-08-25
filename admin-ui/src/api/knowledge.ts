import { get, post } from './request'
import type { GitKnowledgeConfig, KnowledgeContainer } from './git'
import type { KnowledgeLayerAdvice } from './evolution'

export interface KnowledgeSkill {
  id?: string
  name: string
  domain?: string
  trust_level?: string
  source?: string
  path?: string
  description?: string
  usage_count?: number
  success_rate?: number
  updated_at?: string
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
