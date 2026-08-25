import { del, get, post } from './request'

export interface TaskItem {
  id: string
  type: string
  tenant_id: string
  status: string
  priority: number
  progress: number
  created_at: string
  payload?: Record<string, unknown>
  result?: Record<string, unknown>
  error?: string
}

export interface TaskCompareSnapshot {
  task_id: string
  task_type: string
  tenant_id: string
  status: string
  created_at: string
  completed_at?: string | null
  error?: string | null
  summary?: string | null
  capability_id?: string | null
  strategy_id?: string | null
  strategy_score?: number | null
  evaluation_verdict?: string | null
  evaluation_score?: number | null
  replay_of?: string | null
}

export interface TaskCompareResult {
  original: TaskCompareSnapshot
  replay: TaskCompareSnapshot
  diff: {
    score_delta?: number | null
    status_changed: boolean
    capability_changed: boolean
    strategy_changed: boolean
    outcome: string
  }
  validation_record?: {
    id: string
    domain: string
    task_type: string
    input_summary: string
    output_summary: string
    quality_score: number
    metadata: Record<string, unknown>
    created_at: string
  }
}

export function listTasks(limit = 100) {
  return get<TaskItem[]>(`/api/tasks?limit=${limit}`)
}

export function createTask(body: Record<string, unknown>) {
  return post<{ success: boolean; task_id: string }>('/api/tasks', body)
}

export function cancelTaskById(taskId: string) {
  return del<{ success: boolean }>(`/api/tasks/${taskId}`)
}

export function replayTask(taskId: string) {
  return post<{ task_id: string; replay_of: string; tenant_id: string }>(`/api/tasks/${taskId}/replay`, {})
}

export function getTaskCompare(taskId: string) {
  return get<TaskCompareResult>(`/api/tasks/${taskId}/compare`)
}
