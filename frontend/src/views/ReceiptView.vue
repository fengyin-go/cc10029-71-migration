<template>
  <section class="page receipt-page" data-testid="receipt-page" :data-status="view?.status">
    <header class="page-head">
      <div>
        <h2>分发回执核验</h2>
        <p class="page-desc">
          回执 {{ receiptId }} —— 同一笔分发出现在独立站点和教务门户时，在这里核对它属于
          已分发、可续办，还是尚待原入口处理。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" data-testid="receipt-refresh" @click="reload">重新核验</button>
        <RouterLink class="btn" :to="siteLink('/review_meeting')" data-testid="receipt-back-meeting">回到纪要</RouterLink>
        <RouterLink class="btn" :to="siteLink('/improve_task')" data-testid="receipt-back-task">查看诊改任务</RouterLink>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text" data-testid="receipt-error">{{ errorMessage }}</p>

    <template v-if="view">
      <div class="stat-row">
        <article class="stat-card" :class="statusClass">
          <span class="stat-label">当前状态</span>
          <strong class="stat-value" data-testid="receipt-status">{{ view.status }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">对应会议纪要</span>
          <strong class="stat-value" data-testid="receipt-meeting">#{{ view.meetingId }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">实际发出的任务</span>
          <strong class="stat-value" data-testid="receipt-task">{{ view.taskId ?? '—' }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">请求来源</span>
          <strong class="stat-value" data-testid="receipt-sites">{{ siteNames }}</strong>
        </article>
      </div>

      <p class="receipt-message" data-testid="receipt-message">{{ view.message }}</p>

      <table class="data-table">
        <tbody>
          <tr><th>回执编号</th><td data-testid="receipt-id">{{ view.receipt }}</td></tr>
          <tr><th>处理状态</th><td>{{ view.status }}</td></tr>
          <tr><th>任务状态</th><td>{{ view.taskStatus ?? '—' }}</td></tr>
          <tr><th>完成分发的入口</th><td>{{ view.originSiteLabel }}</td></tr>
          <tr><th>收到请求的入口</th><td>{{ siteNames }}</td></tr>
          <tr><th>同一回执请求数</th><td>{{ view.requestCount }}</td></tr>
          <tr><th>是否已认领</th><td>{{ view.claimed ? '已认领' : '未认领' }}</td></tr>
          <tr><th>业务实例</th><td data-testid="receipt-instance">{{ view.storeInstance }}</td></tr>
          <tr><th>当前入口</th><td>{{ currentSiteLabel }}</td></tr>
        </tbody>
      </table>

      <p v-if="view.awaitingOriginal" class="notice notice-wait" data-testid="receipt-wait">
        原入口的分发请求仍在途中，请点开原回执核验后再办理；当前入口不会写入新的任务。
      </p>
      <p v-else-if="view.canResume" class="notice notice-resume" data-testid="receipt-resume">
        任务 #{{ view.taskId }} 已实际发出且仍待认领，可在当前入口续办。
      </p>
      <p v-else class="notice" data-testid="receipt-done">
        任务 #{{ view.taskId }} 已实际发出，重复提交不会再次写入。
      </p>
    </template>

    <p v-else-if="!errorMessage" class="empty-state">正在读取回执…</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { loadReceipt, loadMeetingReceipt } from '@/api/backend-service'
import { SITE_LABEL } from '@/api/client'
import { siteLink } from '@/api/entry'
import type { ReceiptView } from '@/data/types'

const props = defineProps<{ receipt: string }>()
const view = ref<ReceiptView | null>(null)
const errorMessage = ref('')

const receiptId = computed(() => props.receipt)
const currentSiteLabel = SITE_LABEL
const statusClass = computed(() => {
  if (!view.value) return ''
  if (view.value.awaitingOriginal) return 'status-wait'
  if (view.value.canResume) return 'status-resume'
  return 'status-done'
})
const siteNames = computed(() =>
  (view.value?.sites ?? [])
    .map((site) => (site === 'portal' ? '教务门户' : '独立站点'))
    .join('、'),
)

async function reload() {
  errorMessage.value = ''
  try {
    view.value = /^\d+$/.test(props.receipt)
      ? await loadMeetingReceipt(Number(props.receipt))
      : await loadReceipt(props.receipt)
  } catch (error) {
    view.value = null
    errorMessage.value = error instanceof Error ? error.message : '回执读取失败'
  }
}

onMounted(reload)
watch(() => props.receipt, reload)
</script>
