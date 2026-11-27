<template>
  <section class="page" :data-module="meta.key">
    <header class="page-head">
      <div>
        <h2>{{ meta.name }}</h2>
        <p class="page-desc">{{ meta.desc }}</p>
        <p class="entry-hint" data-testid="entry-hint">
          当前入口：{{ SITE_LABEL }} · 业务实例 {{ instanceId || '—' }}
          <template v-if="highlightId"> · 正在定位记录 #{{ highlightId }}</template>
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">
          登记{{ meta.entity }}
        </button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">
          导出{{ meta.name }}清单
        </button>
        <RouterLink
          v-if="isMeetingModule"
          class="btn"
          :to="siteLink(`/receipts/${receiptId || 'M-' + highlightId}`)"
          data-testid="open-receipt"
        >
          核验分发回执
        </RouterLink>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="status-legend">
      <span v-for="item in statusSummary" :key="item.status" class="legend-item">
        {{ item.status }}：{{ item.count }}
      </span>
    </p>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in meta.fields" :key="column">{{ column }}</th>
          <th>当前状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          :data-testid="`row-${row.id}`"
          :data-status="String(row.status)"
          :class="{ 'row-highlight': Number(row.id) === Number(highlightId) }"
        >
          <td v-for="column in meta.fields" :key="column">{{ row[column] ?? '—' }}</td>
          <td>
            {{ row.status }}
            <span
              v-if="row.receiptView"
              class="receipt-chip"
              :class="receiptChipClass(row.receiptView.status)"
              :data-testid="`row-receipt-${row.id}`"
            >
              {{ row.receiptView.receipt }} · {{ row.receiptView.status }}
            </span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actionsFor(row)"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="meta.fields.length + 2" class="empty-state">
            暂无{{ meta.name }}数据，可先登记{{ meta.entity }}
          </td>
        </tr>
      </tbody>
    </table>

    <p v-if="receiptNotice" class="notice" :class="receiptNoticeClass" data-testid="action-notice">
      {{ receiptNotice }}
      <RouterLink
        v-if="noticeReceipt"
        :to="siteLink(`/receipts/${noticeReceipt}`)"
        data-testid="notice-receipt-link"
      >
        查看回执 {{ noticeReceipt }}
      </RouterLink>
    </p>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记{{ meta.entity }}</h3>
        <label v-for="field in meta.fields" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ meta.name }}记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  beginReceipt,
  createEntry,
  downloadEntries,
  listEntries,
  moduleMeta,
  runAction as applyAction,
} from '@/api/backend-service'
import { SITE, SITE_LABEL } from '@/api/client'
import { siteLink } from '@/api/entry'
import type { EntryRow, ReceiptStatus } from '@/data/types'

const props = defineProps<{ moduleKey: string; entryId?: string }>()
const meta = moduleMeta(props.moduleKey)
const rows = ref<EntryRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const instanceId = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = meta.fields.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})
const receiptNotice = ref('')
const receiptNoticeClass = ref('')
const noticeReceipt = ref('')

const highlightId = computed(() => (props.entryId ? Number(props.entryId) : 0))
const isMeetingModule = computed(() => meta.key === 'review_meeting')
const isTaskModule = computed(() => meta.key === 'improve_task')

/** 当前定位记录的显式回执号（没有就让回执页按 M-<纪要编号> 兜底）。 */
const receiptId = computed(() => {
  const row = rows.value.find((item) => Number(item.id) === highlightId.value)
  if (!row) return ''
  return String(row["回执编号"] ?? row.receipt ?? '')
})

const stats = computed(() => [
  { label: meta.metrics[0], value: total.value },
  { label: meta.metrics[1], value: rows.value.filter((row) => row.status === meta.statuses[1]).length },
  {
    label: meta.metrics[2],
    value: rows.value.filter((row) => row.status === meta.statuses[meta.statuses.length - 1]).length,
  },
])
const statusSummary = computed(() =>
  meta.statuses.map((status) => ({
    status,
    count: rows.value.filter((row) => String(row.status) === status).length,
  })),
)

function receiptChipClass(status: ReceiptStatus) {
  if (status === '尚待原入口处理') return 'chip-wait'
  if (status === '可续办') return 'chip-resume'
  return 'chip-done'
}

/** 任务动作按状态收紧：只有实际发出、仍在待认领的任务才给出「认领任务」。 */
function actionsFor(row: EntryRow): string[] {
  if (!isTaskModule.value) return meta.actions
  return meta.actions.filter((action) => {
    if (action === '认领任务') {
      return row.status === '待认领' || row.status === '草稿'
    }
    if (action === '申请验收') return row.status === '执行中'
    return true
  })
}

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  errorMessage.value = ''
  try {
    await downloadEntries(meta.key, filters.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(meta.fields.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const result = await createEntry(meta.key, createValues.value)
    if (!result.ok) throw new Error(result.message)
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: EntryRow) {
  errorMessage.value = ''
  receiptNotice.value = ''
  noticeReceipt.value = ''
  try {
    const receipt = row["回执编号"] ? String(row["回执编号"]) : undefined
    // 分发前先在原入口登记「在途」回执：另一个入口此时只能看到尚待原入口处理。
    if (meta.key === 'review_meeting' && action === '分发给教师' && SITE === 'legacy') {
      const begun = await beginReceipt(Number(row.id), receipt)
      if (!begun.ok) throw new Error(begun.message)
    }
    const result = await applyAction(meta.key, Number(row.id), action, { receipt })
    if (!result.ok && !result.receipt) throw new Error(result.message)
    receiptNotice.value = result.message
    receiptNoticeClass.value = result.receipt?.status === '尚待原入口处理' ? 'notice-wait' : ''
    if (result.receipt?.receipt) noticeReceipt.value = String(result.receipt.receipt)
    if (!result.ok) errorMessage.value = result.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const payload = await listEntries(meta.key, filters.value)
    rows.value = payload.items
    total.value = payload.total
    if (payload.instance) instanceId.value = payload.instance
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '业务列表读取失败'
  }
}

onMounted(reload)
</script>
