import { get, post } from './request'

export interface GitKnowledgeRepo {
  name: string
  full_name: string
  url: string
  branch: string
  private: boolean
}

export interface GitKnowledgeConfig {
  provider?: string
  api_base?: string
  base_url?: string
  namespace?: string
  base_name?: string
  bootstrapped_at?: string
  repos?: Record<string, GitKnowledgeRepo>
}

export interface RepoIndexEntry {
  id?: string
  type?: string
  title: string
  summary?: string
  keywords?: string[]
  path?: string
  source?: string
}

export interface GitKnowledgeRepoIndexItem {
  repo_key: string
  full_name: string
  branch: string
  url?: string
  scanned_at?: string
  index_path?: string | null
  root_paths?: string[]
  entry_count?: number
  entries?: RepoIndexEntry[]
}

export interface GitKnowledgeRepoIndex {
  tenant_id: string
  updated_at?: string | null
  repos: Record<string, GitKnowledgeRepoIndexItem>
}

export interface GitKnowledgeRepoIndexSummary {
  updated_at?: string | null
  repo_count: number
  indexed_repo_count: number
  total_entries: number
  repos: Array<{
    repo_key: string
    index_path?: string | null
    entry_count: number
    scanned_at?: string
  }>
}

export interface KnowledgeContainer {
  id: string
  name: string
  purpose: string
  backend: string
  scope: string
  writable: boolean
  status: string
  location: string
  provider?: string
  branch?: string
  repo_full_name?: string
  metadata?: Record<string, unknown>
}

export function getGitProviderStatus(tenantId: string) {
  return get<{
    provider: string
    api_base: string
    has_user_token: boolean
    tenant_id: string
    git_knowledge: GitKnowledgeConfig
    repo_index: GitKnowledgeRepoIndex
    repo_index_summary: GitKnowledgeRepoIndexSummary
    knowledge_containers: KnowledgeContainer[]
  }>(`/api/git/provider/status?tenant_id=${encodeURIComponent(tenantId)}`)
}

export function getGitKnowledgeIndexTemplate(tenantId: string) {
  return get<{
    tenant_id: string
    template: {
      schema_version: string
      tenant_id: string
      generated_at: string
      description?: string
      entries: RepoIndexEntry[]
    }
    repo_index: GitKnowledgeRepoIndex
    repo_index_summary: GitKnowledgeRepoIndexSummary
  }>(`/api/tenants/${encodeURIComponent(tenantId)}/git-knowledge/index-template`)
}

export function scanTenantGitKnowledge(tenantId: string) {
  return post<{
    tenant_id: string
    provider: string
    scanned: Record<string, GitKnowledgeRepoIndexItem>
    errors: Array<{ repo_key: string; error: string }>
    repo_index: GitKnowledgeRepoIndex
    repo_index_summary: GitKnowledgeRepoIndexSummary
  }>(`/api/tenants/${encodeURIComponent(tenantId)}/git-knowledge/scan`, {})
}

export function exportGitKnowledgeIndexTemplate(
  tenantId: string,
  payload: {
    repo_key?: string
    file_path?: string
    scan_after_write?: boolean
  } = {}
) {
  return post<{
    tenant_id: string
    repo_key: string
    file_path: string
    repo_full_name: string
    repo_url?: string
    branch: string
    scan_after_write: boolean
    scan_result?: GitKnowledgeRepoIndexItem | { repo_key: string; error: string } | null
    repo_index: GitKnowledgeRepoIndex
    repo_index_summary: GitKnowledgeRepoIndexSummary
  }>(`/api/tenants/${encodeURIComponent(tenantId)}/git-knowledge/index-template/export`, payload)
}

export function bootstrapTenantGitKnowledge(
  tenantId: string,
  payload: {
    base_name?: string
    private?: boolean
    provider?: string
    api_base?: string
    base_url?: string
    namespace?: string
  }
) {
  return post<{
    tenant_id: string
    git_knowledge: GitKnowledgeConfig
    knowledge_containers: KnowledgeContainer[]
  }>(`/api/tenants/${encodeURIComponent(tenantId)}/git-knowledge/bootstrap`, payload)
}
