/**
 * 真实后端联调：直接渲染真实组件，走「旧链接打开纪要 → 切入门户领取 → 回原入口核对」。
 *
 * 需要本机后端运行在 127.0.0.1:8000；不可用时整组跳过，避免影响常规单元测试。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeAll, describe, expect, it } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'

const BACKEND = 'http://127.0.0.1:8000'

async function backendUp(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND}/api/health`)
    return res.ok
  } catch {
    return false
  }
}

const up = await backendUp()

describe.skipIf(!up)('portal migration flow (live backend)', () => {
  let WorkbenchView: typeof import('@/views/WorkbenchView.vue')['default']
  let ReceiptView: typeof import('@/views/ReceiptView.vue')['default']
  let SITE: string
  let meetingId = 0
  let taskId = 0

  beforeAll(async () => {
    window.history.replaceState({}, '', '/portal/')
    // 相对路径请求转发到真实后端。
    const originalFetch = globalThis.fetch
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString()
      return originalFetch(url.startsWith('http') ? url : `${BACKEND}${url}`, init)
    }) as typeof fetch

    const [{ default: W }, { default: R }, client] = await Promise.all([
      import('@/views/WorkbenchView.vue'),
      import('@/views/ReceiptView.vue'),
      import('@/api/client'),
    ])
    WorkbenchView = W
    ReceiptView = R
    SITE = client.SITE
  })

  function makeRouter() {
    return createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/portal/:moduleKey/:entryId?', component: { template: '<div/>' } },
        { path: '/portal/receipts/:receipt', component: { template: '<div/>' } },
      ],
    })
  }

  async function mountAt(component: unknown, path: string, props: Record<string, string>) {
    const router = makeRouter()
    await router.push(path)
    const wrapper = mount(component as never, {
      props: props as never,
      global: {
        plugins: [router],
        stubs: { RouterLink: { props: ['to'], template: '<a :data-to="to"><slot/></a>' } },
      },
    })
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 120))
    await flushPromises()
    return wrapper
  }

  it('sees the portal entry and keeps tasks on the shared instance', async () => {
    expect(SITE).toBe('portal')

    // 每次从干净的示例数据与空回执账本开始。
    await fetch(`${BACKEND}/portal/api/admin/reset`, { method: 'POST' })

    // 通过接口准备一条已签认纪要（模拟原入口）。
    const created = await fetch(`${BACKEND}/api/review_meeting?site=legacy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        values: {
          会议主题: '门户联调 M-56',
          参会人员: '全体教师',
          召开日期: '2026-11-01',
          决议事项: '成立任务组并落实',
          备注说明: '回执 M-56',
        },
      }),
    }).then((res) => res.json())
    meetingId = created.entry.id

    await fetch(`${BACKEND}/api/review_meeting/${meetingId}/actions?site=legacy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: '签认纪要' }),
    })

    // 原入口登记在途回执，门户先看到「尚待原入口处理」。
    await fetch(`${BACKEND}/api/receipts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ meetingId, receipt: 'M-56', site: 'legacy' }),
    })
    const receiptView = await mountAt(
      ReceiptView as never,
      '/portal/receipts/M-56',
      { receipt: 'M-56' },
    )
    expect(receiptView.get('[data-testid="receipt-status"]').text()).toBe('尚待原入口处理')

    // 原入口完成分发。
    const done = await fetch(
      `${BACKEND}/api/review_meeting/${meetingId}/actions?site=legacy&receipt=M-56`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: '分发给教师' }),
      },
    ).then((res) => res.json())
    taskId = done.entry.taskId
    expect(taskId).toBeGreaterThan(0)

    // 门户重复提交：可续办。
    const duplicate = await fetch(
      `${BACKEND}/portal/api/review_meeting/${meetingId}/actions?site=portal&receipt=M-56`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: '分发给教师' }),
      },
    ).then((res) => res.json())
    expect(duplicate.status).toBe('可续办')

    // 门户任务页渲染：同一笔任务只出现一次，带可续办徽标。
    const taskPage = await mountAt(
      WorkbenchView as never,
      `/portal/improve_task/${taskId}`,
      { moduleKey: 'improve_task', entryId: String(taskId) },
    )
    const autoRows = taskPage.findAll('tr[data-testid]').filter((row) =>
      row.text().includes('meeting:'),
    )
    expect(autoRows).toHaveLength(1)
    expect(taskPage.get(`[data-testid="row-receipt-${taskId}"]`).text()).toContain('可续办')

    // 门户领取任务。
    await taskPage.get(`[data-testid="action-${taskId}-认领任务"]`).trigger('click')
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 150))
    await flushPromises()

    // 回原入口核对：任务编号仍指回原纪要，任务已被门户认领。
    const [meeting, task, receipt] = await Promise.all([
      fetch(`${BACKEND}/api/review_meeting/${meetingId}`).then((r) => r.json()),
      fetch(`${BACKEND}/api/improve_task/${taskId}`).then((r) => r.json()),
      fetch(`${BACKEND}/api/receipts/M-56`).then((r) => r.json()),
    ])
    expect(meeting.taskId).toBe(taskId)
    expect(task.来源会议).toBe(meetingId)
    expect(task.status).toBe('执行中')
    expect(task.claimedSite).toBe('教务门户')
    expect(receipt.taskId).toBe(taskId)
    expect(receipt.claimed).toBe(true)

    // 回切也要点开原回执核验：原入口的回执页显示已分发与任务号。
    const legacyReceipt = await mountAt(
      ReceiptView as never,
      '/portal/receipts/M-56',
      { receipt: 'M-56' },
    )
    expect(legacyReceipt.get('[data-testid="receipt-status"]').text()).toBe('已分发')
    expect(legacyReceipt.get('[data-testid="receipt-task"]').text()).toContain(String(taskId))
    expect(legacyReceipt.get('[data-testid="receipt-instance"]').text()).toBe(task.storeInstance)

    // 旧链接打开纪要仍能看到回执与任务号。
    const oldLink = await mountAt(
      WorkbenchView as never,
      `/portal/review_meeting/${meetingId}`,
      { moduleKey: 'review_meeting', entryId: String(meetingId) },
    )
    expect(oldLink.get(`[data-testid="row-${meetingId}"]`).classes()).toContain('row-highlight')
    expect(oldLink.get(`[data-testid="row-receipt-${meetingId}"]`).text()).toContain('M-56')
  })
})
