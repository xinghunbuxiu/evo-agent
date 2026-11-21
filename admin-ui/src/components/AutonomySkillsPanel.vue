<template>
  <div class="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 class="text-lg font-semibold text-slate-900">自治技能产出</h2>
      <div class="mt-4 grid gap-3 sm:grid-cols-3">
        <div class="rounded-xl bg-slate-50 px-4 py-3 text-center">
          <div class="text-2xl font-bold text-slate-900">{{ summary?.auto_generated_total ?? 0 }}</div>
          <div class="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">Generated</div>
        </div>
        <div class="rounded-xl bg-amber-50 px-4 py-3 text-center">
          <div class="text-2xl font-bold text-amber-700">{{ summary?.auto_draft_count ?? 0 }}</div>
          <div class="mt-1 text-xs uppercase tracking-[0.16em] text-amber-500">Draft</div>
        </div>
        <div class="rounded-xl bg-emerald-50 px-4 py-3 text-center">
          <div class="text-2xl font-bold text-emerald-700">{{ summary?.auto_verified_count ?? 0 }}</div>
          <div class="mt-1 text-xs uppercase tracking-[0.16em] text-emerald-500">Verified</div>
        </div>
      </div>
      <p class="mt-4 text-sm text-slate-500">系统从经验里长出来的技能，不包含纯手工导入。</p>
    </div>
    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="flex items-center justify-between gap-3">
        <h2 class="text-lg font-semibold text-slate-900">最近自治技能</h2>
        <span class="text-xs text-slate-400">{{ recentSkills.length }} 条</span>
      </div>
      <div v-if="!recentSkills.length" class="py-10 text-center text-sm text-slate-500">
        还没有检测到最近的自治技能产出。
      </div>
      <div v-else class="mt-4 space-y-3">
        <div
          v-for="skill in recentSkills"
          :key="skill.id || `${skill.domain}-${skill.name}`"
          class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="text-sm font-medium text-slate-900">{{ skill.name }}</div>
            <StatusBadge :status="skill.trust_level || 'draft'" />
          </div>
          <div class="mt-2 text-xs text-slate-500">
            {{ skill.domain || 'unknown' }} | {{ skill.source || 'local' }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import StatusBadge from './StatusBadge.vue'
import type { KnowledgeSkillsPayload } from '../api/knowledge'

defineProps<{
  summary: KnowledgeSkillsPayload['autonomy_skill_summary'] | null
  recentSkills: NonNullable<KnowledgeSkillsPayload['recent_autonomy_skills']>
}>()
</script>
