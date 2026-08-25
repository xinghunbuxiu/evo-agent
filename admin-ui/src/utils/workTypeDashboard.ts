import type { AutonomyFormalTask, ChildMemberRuntimeProfile } from '../api/plugins'
import type { WorkTypeItem } from '../api/workTypes'
import { resolveMemberWorkTypeId } from './formalTaskRecommendation'

export type WorkTypeDashboardMember = {
  member_id: string
  name: string
  taskStatus?: string
  taskTitle?: string
  link: string
}

export type WorkTypeDashboardRow = {
  work_type_id: string
  title: string
  memberCount: number
  activeTaskCount: number
  pendingSubmitCount: number
  pendingReviewCount: number
  members: WorkTypeDashboardMember[]
}

const memberWorkspaceLink = (memberId: string) => (
  `/organization/child/${encodeURIComponent(memberId)}/workspace`
)

const activeMembers = (members: ChildMemberRuntimeProfile[]) => (
  members.filter((item) => String(item.status || 'active') !== 'archived')
)

const tasksForMember = (tasks: AutonomyFormalTask[], memberId: string) => (
  tasks.filter((item) => String(item.member_id || '').trim() === memberId)
)

const latestOpenTask = (tasks: AutonomyFormalTask[]) => (
  tasks.find((item) => !['approved'].includes(String(item.status || '').trim()))
  || tasks[0]
  || null
)

export function buildWorkTypeDashboardRows(input: {
  workTypes: WorkTypeItem[]
  members: ChildMemberRuntimeProfile[]
  tasks: AutonomyFormalTask[]
}): WorkTypeDashboardRow[] {
  const { workTypes, members, tasks } = input
  const roster = activeMembers(members).filter((item) => (
    String(item.primary_role || '').trim() !== 'talent_development'
  ))

  const rows: WorkTypeDashboardRow[] = workTypes.map((workType) => {
    const workTypeId = String(workType.work_type_id || '').trim()
    const matchedMembers = roster.filter((member) => resolveMemberWorkTypeId(member) === workTypeId)
    const memberSummaries: WorkTypeDashboardMember[] = matchedMembers.map((member) => {
      const memberId = String(member.member_id || '').trim()
      const memberTasks = tasksForMember(tasks, memberId)
      const openTask = latestOpenTask(memberTasks)
      return {
        member_id: memberId,
        name: String(member.name || member.identity?.name || memberId),
        taskStatus: String(openTask?.status || '').trim() || undefined,
        taskTitle: String(openTask?.title || '').trim() || undefined,
        link: memberWorkspaceLink(memberId),
      }
    })
    const activeTaskCount = memberSummaries.filter((item) => item.taskStatus && item.taskStatus !== 'approved').length
    const pendingSubmitCount = memberSummaries.filter((item) => item.taskStatus === 'assigned').length
    const pendingReviewCount = memberSummaries.filter((item) => item.taskStatus === 'submitted').length
    return {
      work_type_id: workTypeId,
      title: String(workType.title || workTypeId),
      memberCount: matchedMembers.length,
      activeTaskCount,
      pendingSubmitCount,
      pendingReviewCount,
      members: memberSummaries,
    }
  })

  return rows
}

export function formatTaskStatusLabel(status?: string | null): string {
  const normalized = String(status || '').trim()
  if (!normalized) return '无任务'
  if (normalized === 'assigned') return '待提交'
  if (normalized === 'submitted') return '待确认'
  if (normalized === 'approved') return '已完成'
  return normalized
}
