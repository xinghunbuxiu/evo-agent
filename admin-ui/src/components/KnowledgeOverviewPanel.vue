<template>
  <div class="space-y-5">
    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="flex items-center justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-slate-900">三层知识架构</h2>
          <p class="mt-1 text-sm text-slate-500">服务端做分析与建议，项目做上下文，Git 做长期容器，平台共享只接收经过复盘验证的经验。</p>
        </div>
        <div class="text-xs text-slate-400">tenant {{ tenantId || 'default' }}</div>
      </div>
      <div class="mt-4 grid gap-3 md:grid-cols-3">
        <article class="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
          <div class="text-xs uppercase tracking-[0.16em] text-emerald-700">Private Brain</div>
          <div class="mt-2 text-2xl font-bold text-slate-900">{{ privateContainerCount }}</div>
          <div class="mt-2 text-sm text-slate-600">租户私有知识、经验、报告只在自己的空间里生长。</div>
          <div class="mt-3 text-xs text-slate-500">share mode: {{ shareModeLabel }}</div>
        </article>
        <article class="rounded-2xl border border-sky-200 bg-sky-50 p-4">
          <div class="text-xs uppercase tracking-[0.16em] text-sky-700">Project Containers</div>
          <div class="mt-2 text-2xl font-bold text-slate-900">{{ projectContainerCount }}</div>
          <div class="mt-2 text-sm text-slate-600">按工种、项目、经验仓拆分容器，避免所有知识互相污染。</div>
          <div class="mt-3 text-xs text-slate-500">indexed repos: {{ indexedRepoCount }}</div>
        </article>
        <article class="rounded-2xl border border-fuchsia-200 bg-fuchsia-50 p-4">
          <div class="text-xs uppercase tracking-[0.16em] text-fuchsia-700">Platform Shared</div>
          <div class="mt-2 text-2xl font-bold text-slate-900">{{ sharedContainerCount }}</div>
          <div class="mt-2 text-sm text-slate-600">经过 review 和验证后，才进入平台共享层给后续租户复用。</div>
          <div class="mt-3 text-xs text-slate-500">{{ platformPromotionLabel }}</div>
        </article>
      </div>
      <div v-if="knowledgeLayerAdvice" class="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-sm font-semibold text-slate-900">系统自动分层建议</div>
            <div class="mt-1 text-sm text-slate-600">{{ knowledgeLayerAdvice.headline }}</div>
          </div>
          <span class="rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-700">
            next {{ knowledgeLayerAdvice.recommended_next_layer }}
          </span>
        </div>
        <div class="mt-3 text-sm text-slate-500">{{ knowledgeLayerAdvice.recommendation_reason }}</div>
        <div class="mt-4 grid gap-3 md:grid-cols-3">
          <div
            v-for="layer in knowledgeLayerAdvice.layers"
            :key="layer.key"
            class="rounded-xl bg-white px-4 py-3"
          >
            <div class="flex items-center justify-between gap-3">
              <div class="text-sm font-medium text-slate-900">{{ layer.label }}</div>
              <span class="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{{ layer.status }}</span>
            </div>
            <div class="mt-2 text-2xl font-bold text-slate-900">{{ layer.count }}</div>
            <div class="mt-2 text-xs text-slate-500">{{ layer.reason }}</div>
            <div class="mt-2 text-xs text-slate-400">{{ layer.next_action }}</div>
          </div>
        </div>
        <ul v-if="knowledgeLayerAdvice.next_actions?.length" class="mt-4 space-y-1 text-sm text-slate-600">
          <li v-for="item in knowledgeLayerAdvice.next_actions" :key="item">• {{ item }}</li>
        </ul>
      </div>
    </div>

    <div class="grid gap-4 md:grid-cols-4">
      <div class="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
        <div class="text-2xl font-bold text-teal-600">{{ stats.total }}</div>
        <div class="text-sm text-slate-500">本地技能</div>
      </div>
      <div class="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
        <div class="text-2xl font-bold text-yellow-600">{{ stats.draft }}</div>
        <div class="text-sm text-slate-500">草稿</div>
      </div>
      <div class="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
        <div class="text-2xl font-bold text-green-600">{{ stats.verified }}</div>
        <div class="text-sm text-slate-500">已验证</div>
      </div>
      <div class="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
        <div class="text-2xl font-bold" :class="gitReady ? 'text-emerald-600' : 'text-slate-400'">
          {{ gitReady ? 'Ready' : 'Pending' }}
        </div>
        <div class="text-sm text-slate-500">Git 知识层</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { KnowledgeSkillsPayload } from '../api/knowledge'

defineProps<{
  tenantId: string
  privateContainerCount: number
  projectContainerCount: number
  sharedContainerCount: number
  shareModeLabel: string
  platformPromotionLabel: string
  indexedRepoCount: number
  knowledgeLayerAdvice: KnowledgeSkillsPayload['knowledge_layer_advice'] | null
  stats: { total: number; draft: number; verified: number }
  gitReady: boolean
}>()
</script>
